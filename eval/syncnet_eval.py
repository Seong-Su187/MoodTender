"""
eval/syncnet_eval.py
AI휴먼 정량평가 5번: 립싱크 품질 (LSE-C/D) - SyncNet으로 평가

eval/outputs/<decode-label>/<id>/output.mp4 에 대해
joonson/syncnet_python(eval/syncnet/syncnet_python)의 얼굴 검출/트래킹 +
SyncNet 모델로 LSE-C(confidence)/LSE-D(distance)를 계산한다.
LSE-C는 높을수록, LSE-D는 낮을수록 립싱크 품질이 좋다.

사용법 (project root에서):
  backend\\MuseTalk\\venv\\Scripts\\python.exe eval\\syncnet_eval.py --decode-label decode50
"""

import io
import json
import argparse
import sys
import subprocess
from pathlib import Path
from types import SimpleNamespace

import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "eval" / "outputs"
LOG_DIR = PROJECT_ROOT / "eval" / "logs"
SYNCNET_DIR = PROJECT_ROOT / "eval" / "syncnet" / "syncnet_python"
WORK_DIR = PROJECT_ROOT / "eval" / "syncnet" / "work"


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

sys.path.insert(0, str(SYNCNET_DIR))


def run_face_pipeline(videofile: Path, reference: str, min_track: int) -> Path:
    """run_pipeline.py로 얼굴 검출/트래킹/크롭(.avi)을 생성하고 pycrop 디렉터리를 반환한다."""
    cmd = [
        sys.executable, "run_pipeline.py",
        "--videofile", str(Path(videofile).resolve()),
        "--reference", reference,
        "--data_dir", str(WORK_DIR),
        "--min_track", str(min_track),
        "--overwrite",
    ]
    proc = subprocess.run(cmd, cwd=str(SYNCNET_DIR), capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise RuntimeError(f"run_pipeline.py 실패 (reference={reference})")
    return WORK_DIR / "pycrop" / reference


def evaluate_item(syncnet, videofile: Path, reference: str, min_track: int, batch_size: int, vshift: int):
    crop_dir = run_face_pipeline(videofile, reference, min_track)
    crops = sorted(crop_dir.glob("0*.avi")) if crop_dir.exists() else []
    if not crops:
        return None

    opt = SimpleNamespace(
        tmp_dir=str(WORK_DIR / "pytmp"),
        reference=reference,
        batch_size=batch_size,
        vshift=vshift,
    )

    best = None
    for crop in crops:
        offset, conf, dists = syncnet.evaluate(opt, videofile=str(crop))
        mdist = dists.mean(axis=0)
        lse_d = float(mdist.min())
        lse_c = float(conf)
        n_frames = dists.shape[0]
        if best is None or n_frames > best["n_frames"]:
            best = {"lse_c": lse_c, "lse_d": lse_d, "n_frames": n_frames, "offset": int(offset)}

    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decode-label", default="decode50")
    parser.add_argument("--min-track", type=int, default=50, help="최소 얼굴 트랙 길이(프레임)")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--vshift", type=int, default=15)
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 N개 항목만 실행 (디버그용)")
    parser.add_argument("--force", action="store_true", help="이미 syncnet.jsonl에 있어도 다시 채점")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log_file = open(LOG_DIR / f"{args.decode_label}_syncnet.log", "w", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, _log_file)
    sys.stderr = _Tee(sys.__stderr__, _log_file)

    out_dir = OUTPUT_ROOT / args.decode_label
    if not out_dir.exists():
        raise SystemExit(f"출력 디렉터리가 없음: {out_dir} (먼저 run_pipeline.py를 실행하세요)")

    item_dirs = sorted(p for p in out_dir.glob("[0-9][0-9]") if p.is_dir())
    if args.limit:
        item_dirs = item_dirs[: args.limit]

    result_path = out_dir / "syncnet.jsonl"
    done: dict[int, dict] = {}
    if result_path.exists() and not args.force:
        for line in result_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row

    from SyncNetInstance import SyncNetInstance

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[SyncNet 로딩 중...] device={device}")
    syncnet = SyncNetInstance(device=device)
    syncnet.loadParameters(str(SYNCNET_DIR / "data" / "syncnet_v2.model"))

    results = []
    for item_dir in item_dirs:
        item_id = int(item_dir.name)
        if item_id in done:
            print(f"[SKIP] id={item_id:02d} (이미 채점됨)", flush=True)
            results.append(done[item_id])
            continue

        video_path = item_dir / "output.mp4"
        if not video_path.exists():
            print(f"[SKIP] id={item_id:02d} (output.mp4 없음)", flush=True)
            continue

        reference = item_dir.name  # "01".."40"
        score = evaluate_item(syncnet, video_path, reference, args.min_track, args.batch_size, args.vshift)
        if score is None:
            print(f"[{item_id:02d}] 얼굴 트랙을 찾지 못함 (LSE 계산 불가)", flush=True)
            row = {"id": item_id, "LSE-C": None, "LSE-D": None, "n_frames": 0}
        else:
            print(
                f"[{item_id:02d}] LSE-C={score['lse_c']:.3f} LSE-D={score['lse_d']:.3f} "
                f"(frames={score['n_frames']}, offset={score['offset']})",
                flush=True,
            )
            row = {
                "id": item_id,
                "LSE-C": round(score["lse_c"], 4),
                "LSE-D": round(score["lse_d"], 4),
                "n_frames": score["n_frames"],
                "offset": score["offset"],
            }
        results.append(row)

        with open(result_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    valid = [r for r in results if r.get("LSE-C") is not None]
    n = len(valid)
    summary = {
        "decode_label": args.decode_label,
        "n_items": len(results),
        "n_valid": n,
        "avg_LSE_C": round(sum(r["LSE-C"] for r in valid) / n, 4) if n else None,
        "avg_LSE_D": round(sum(r["LSE-D"] for r in valid) / n, 4) if n else None,
    }
    (out_dir / "syncnet_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== SyncNet LSE-C/D 요약 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
