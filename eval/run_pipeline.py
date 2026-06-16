"""
eval/run_pipeline.py
AI휴먼 정량평가: testset.jsonl의 각 문항에 대해
  1) bartender_chain으로 LLM 응답 생성 (대화 G-Eval용)
  2) TTS로 음성 생성 (CER/WER용)
  3) MuseTalk(inference_stream)으로 영상 생성 + TTFB/FPS/완료율 측정 (LSE-C/D, 시스템지표용)
을 수행하고 eval/outputs/<decode-label>/<id>/ 에 결과를 저장한다.

사용법 (project root에서):
  backend\\MuseTalk\\venv\\Scripts\\python.exe eval\\run_pipeline.py --decode-label decode50 --limit 2
"""

import sys
import os
import io
import re
import json
import time
import argparse
import asyncio
import contextlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
OUTPUT_ROOT = PROJECT_ROOT / "eval" / "outputs"
LOG_DIR = PROJECT_ROOT / "eval" / "logs"
TESTSET_PATH = PROJECT_ROOT / "testset.jsonl"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(BACKEND_DIR))

# backend.config는 import 시 MuseTalk 디렉터리로 os.chdir() 한다.
from backend.config import FFMPEG_PATH  # noqa: E402
from backend.services import ml_manager  # noqa: E402
from backend.services.rag_chain import CHAINS, _trim  # noqa: E402
from backend.services.video_audio import tts, get_audio_duration  # noqa: E402

from langchain_core.messages import HumanMessage, AIMessage  # noqa: E402

AVATAR_NAME = "1_towel_wine.mp4"
VOICE = "onyx"
SPEED = 1.0

BATCH_LINE_RE = re.compile(
    r"\[배치(\d+)\]\s+B=\s*(\d+)\s+UNet=\s*([\d.]+)ms\s+VAE=\s*([\d.]+)ms\s+합=\s*([\d.]+)ms"
)


class _Tee(io.TextIOBase):
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)
        return len(data)

    def flush(self):
        for s in self._streams:
            s.flush()


def _parse_batch_log(log_text: str) -> dict:
    batches = []
    for m in BATCH_LINE_RE.finditer(log_text):
        batches.append({
            "batch": int(m.group(1)),
            "B": int(m.group(2)),
            "unet_ms": float(m.group(3)),
            "vae_ms": float(m.group(4)),
            "total_ms": float(m.group(5)),
        })
    total_frames = sum(b["B"] for b in batches)
    total_gpu_ms = sum(b["total_ms"] for b in batches)
    avg_vae_ms = (sum(b["vae_ms"] for b in batches) / len(batches)) if batches else 0.0
    avg_unet_ms = (sum(b["unet_ms"] for b in batches) / len(batches)) if batches else 0.0
    return {
        "batches": batches,
        "total_frames": total_frames,
        "total_gpu_ms": total_gpu_ms,
        "avg_vae_ms": avg_vae_ms,
        "avg_unet_ms": avg_unet_ms,
    }


async def _llm_reply(bartender_chain, user_input: str, history: list) -> tuple[str, float]:
    t0 = time.perf_counter()
    raw_reply = await bartender_chain.ainvoke({
        "memory_context": "관련 기억 없음",
        "past_chat_context": "관련 과거 대화 없음",
        "health_context": "건강 데이터 없음",
        "expert_knowledge": "",
        "emotion_context": "감정 사전 없음",
        "history": history,
        "user_input": user_input,
        "cocktail_hint": "아직은 칵테일을 추천하지 말고 손님의 이야기를 더 들어준다.",
    })
    latency = time.perf_counter() - t0
    reply = _trim(raw_reply, SPEED)
    return reply, latency


async def run_item(item: dict, av, bartender_chain, item_dir: Path, full_decode: bool = False) -> dict:
    item_id = item["id"]
    print(f"\n=== [{item_id}] {item.get('category')} | {item['input'][:40]!r} ===", flush=True)

    # 1. 멀티턴 history 구성 (turns[:-1]을 차례로 모델에 흘려보내 history를 쌓는다)
    history: list = []
    if "turns" in item:
        for turn_text in item["turns"][:-1]:
            turn_reply, _ = await _llm_reply(bartender_chain, turn_text, history)
            history.append(HumanMessage(content=turn_text))
            history.append(AIMessage(content=turn_reply))

    user_input = item["input"]

    # 2. 최종 턴 LLM 응답 (G-Eval 대상)
    reply, llm_latency = await _llm_reply(bartender_chain, user_input, history)
    print(f"[LLM] {llm_latency:.2f}초 → {reply}", flush=True)
    (item_dir / "reply.txt").write_text(reply, encoding="utf-8")

    # 3. TTS (CER/WER 대상)
    audio_path = str(item_dir / "tts.wav")
    t0 = time.perf_counter()
    tts(reply, audio_path, VOICE, SPEED)
    tts_latency = time.perf_counter() - t0
    audio_duration = get_audio_duration(audio_path)
    print(f"[TTS] {tts_latency:.2f}초 (음성 {audio_duration:.2f}초)", flush=True)

    # 4. MuseTalk 스트리밍 추론 (TTFB/FPS/완료율 + LSE-C/D 대상 영상)
    from stream_inference import inference_stream  # MuseTalk 디렉터리 기준 모듈

    video_path = str(item_dir / "output.mp4")
    completed = False
    error = None
    ttfb = None
    chunk_count = 0
    log_buf = io.StringIO()
    t0 = time.perf_counter()
    try:
        with open(video_path, "wb") as f, contextlib.redirect_stdout(_Tee(sys.stdout, log_buf)):
            for chunk in inference_stream(
                av, audio_path, ml_manager.args.fps, FFMPEG_PATH,
                ml_manager.pe, ml_manager.unet, ml_manager.vae, ml_manager.timesteps,
                ml_manager.whisper, ml_manager.audio_processor,
                ml_manager.weight_dtype, ml_manager.device,
                ml_manager.args.audio_padding_length_left,
                ml_manager.args.audio_padding_length_right,
                taesd=ml_manager.taesd_decoder,
                full_decode=full_decode,
            ):
                if ttfb is None:
                    ttfb = time.perf_counter() - t0
                f.write(chunk)
                chunk_count += 1
        total_time = time.perf_counter() - t0
        completed = chunk_count > 0
    except Exception as e:
        total_time = time.perf_counter() - t0
        error = str(e)
        print(f"[ERROR] {e}", flush=True)

    batch_stats = _parse_batch_log(log_buf.getvalue())
    fps = (batch_stats["total_frames"] / total_time) if total_time > 0 else 0.0
    realtime_ratio = (total_time / audio_duration) if audio_duration > 0 else None

    print(
        f"[VIDEO] TTFB={ttfb:.2f}s 총={total_time:.2f}s 프레임={batch_stats['total_frames']} "
        f"FPS={fps:.1f} 실시간비율={realtime_ratio}",
        flush=True,
    )

    metrics = {
        "id": item_id,
        "category": item.get("category"),
        "emotion": item.get("emotion"),
        "input": user_input,
        "output": reply,
        "llm_latency_sec": round(llm_latency, 3),
        "tts_latency_sec": round(tts_latency, 3),
        "audio_duration_sec": round(audio_duration, 3),
        "ttfb_sec": round(ttfb, 3) if ttfb is not None else None,
        "total_video_gen_sec": round(total_time, 3),
        "total_frames": batch_stats["total_frames"],
        "fps": round(fps, 2),
        "avg_unet_ms": round(batch_stats["avg_unet_ms"], 1),
        "avg_vae_ms": round(batch_stats["avg_vae_ms"], 1),
        "realtime_ratio": round(realtime_ratio, 3) if realtime_ratio is not None else None,
        "completed": completed,
        "error": error,
    }
    (item_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metrics


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decode-label", default="decode50")
    parser.add_argument("--full-decode", action="store_true", help="VAE 보간 없이 모든 프레임을 디코딩 (decode100)")
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 N개 문항만 실행 (디버그용)")
    parser.add_argument("--force", action="store_true", help="이미 metrics.json이 있어도 재실행")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log_file = open(LOG_DIR / f"{args.decode_label}_run.log", "w", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, _log_file)
    sys.stderr = _Tee(sys.__stderr__, _log_file)

    out_dir = OUTPUT_ROOT / args.decode_label
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[모델 로딩 중...]", flush=True)
    ml_manager.load_models(full_decode=args.full_decode)
    if not ml_manager.models_ready:
        print(f"[모델 로딩 실패] {ml_manager.loading_error}")
        return

    av = ml_manager.video_avatars.get(AVATAR_NAME)
    if av is None:
        raise RuntimeError(f"아바타를 찾을 수 없음: {AVATAR_NAME} (사용 가능: {list(ml_manager.video_avatars)})")

    _, bartender_chain, *_ = CHAINS

    testset = [json.loads(line) for line in TESTSET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        testset = testset[: args.limit]

    results = []
    for item in testset:
        item_dir = out_dir / f"{item['id']:02d}"
        item_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = item_dir / "metrics.json"
        if metrics_path.exists() and not args.force:
            print(f"[SKIP] id={item['id']} (이미 완료)", flush=True)
            results.append(json.loads(metrics_path.read_text(encoding="utf-8")))
            continue
        metrics = await run_item(item, av, bartender_chain, item_dir, full_decode=args.full_decode)
        results.append(metrics)

    results_path = out_dir / "results.jsonl"
    with open(results_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 시스템 지표 요약
    completed = [r for r in results if r["completed"]]
    n = len(results)
    summary = {
        "decode_label": args.decode_label,
        "n_items": n,
        "completion_rate": round(100 * len(completed) / n, 1) if n else 0,
        "avg_ttfb_sec": round(sum(r["ttfb_sec"] for r in completed) / len(completed), 3) if completed else None,
        "avg_fps": round(sum(r["fps"] for r in completed) / len(completed), 2) if completed else None,
        "avg_realtime_ratio": round(sum(r["realtime_ratio"] for r in completed) / len(completed), 3) if completed else None,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 요약 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
