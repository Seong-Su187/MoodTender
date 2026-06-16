"""
eval/cer_eval.py
AI휴먼 정량평가 4번: 음성 품질 (CER/WER) - Whisper로 되받아쓰기

eval/outputs/<decode-label>/<id>/tts.wav 를 Whisper로 다시 텍스트화해서
reply.txt(=TTS에 넘긴 원문)과 비교해 CER/WER을 계산한다.
한국어는 CER이 주지표, WER은 보조 지표다.

사용법 (project root에서):
  backend\\MuseTalk\\venv\\Scripts\\python.exe eval\\cer_eval.py --decode-label decode50
"""

import io
import sys
import json
import argparse
from pathlib import Path

import whisper
from jiwer import cer, wer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "eval" / "outputs"
LOG_DIR = PROJECT_ROOT / "eval" / "logs"


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decode-label", default="decode50")
    parser.add_argument("--model", default="medium", help="Whisper 모델 크기 (tiny/base/small/medium/large-v3)")
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 N개 항목만 실행 (디버그용)")
    parser.add_argument("--force", action="store_true", help="이미 cer_wer.jsonl에 있어도 다시 채점")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log_file = open(LOG_DIR / f"{args.decode_label}_cer.log", "w", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, _log_file)
    sys.stderr = _Tee(sys.__stderr__, _log_file)

    out_dir = OUTPUT_ROOT / args.decode_label
    if not out_dir.exists():
        raise SystemExit(f"출력 디렉터리가 없음: {out_dir} (먼저 run_pipeline.py를 실행하세요)")

    item_dirs = sorted(p for p in out_dir.glob("[0-9][0-9]") if p.is_dir())
    if args.limit:
        item_dirs = item_dirs[: args.limit]

    cer_path = out_dir / "cer_wer.jsonl"
    done: dict[int, dict] = {}
    if cer_path.exists() and not args.force:
        for line in cer_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row

    print(f"[Whisper 로딩 중...] model={args.model}")
    model = whisper.load_model(args.model)

    results = []
    for item_dir in item_dirs:
        item_id = int(item_dir.name)
        if item_id in done:
            print(f"[SKIP] id={item_id:02d} (이미 채점됨)", flush=True)
            results.append(done[item_id])
            continue

        reply_path = item_dir / "reply.txt"
        audio_path = item_dir / "tts.wav"
        if not reply_path.exists() or not audio_path.exists():
            print(f"[SKIP] id={item_id:02d} (reply.txt/tts.wav 없음)", flush=True)
            continue

        original = reply_path.read_text(encoding="utf-8").strip()
        heard = model.transcribe(str(audio_path), language="ko")["text"].strip()

        item_cer = cer(original, heard)
        item_wer = wer(original, heard)
        print(f"[{item_id:02d}] CER={item_cer:.3f} WER={item_wer:.3f}", flush=True)
        print(f"  원문: {original}", flush=True)
        print(f"  인식: {heard}", flush=True)

        row = {
            "id": item_id,
            "original": original,
            "heard": heard,
            "CER": round(item_cer, 4),
            "WER": round(item_wer, 4),
        }
        results.append(row)

        # 한 항목씩 끝날 때마다 바로 저장 (중간에 끊겨도 이어서 가능)
        with open(cer_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(results)
    summary = {
        "decode_label": args.decode_label,
        "whisper_model": args.model,
        "n_items": n,
        "avg_CER": round(sum(r["CER"] for r in results) / n, 4) if n else None,
        "avg_WER": round(sum(r["WER"] for r in results) / n, 4) if n else None,
    }
    (out_dir / "cer_wer_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== CER/WER 요약 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
