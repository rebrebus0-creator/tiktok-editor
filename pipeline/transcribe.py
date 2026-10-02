"""Transcribe a video with word timestamps (faster-whisper).

Usage: python3 pipeline/transcribe.py <video> <out.json> [--model small] [--language ru]
"""
import argparse
import json

from faster_whisper import WhisperModel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--model", default="small")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--language", default=None)
    a = ap.parse_args()

    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type)
    segments, info = model.transcribe(a.video, language=a.language, word_timestamps=True, vad_filter=True)
    out = {"language": info.language, "duration": info.duration, "segments": []}
    for seg in segments:
        out["segments"].append(
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
                "words": [{"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word} for w in (seg.words or [])],
            }
        )
        print(f"[{seg.start:7.1f}] {seg.text.strip()}", flush=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
