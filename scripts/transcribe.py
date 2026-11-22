"""Transcribe a recording with faster-whisper and keep word-level timestamps for editing.

Usage: python3 scripts/transcribe.py <audio> <out_dir> [model]
Outputs: <stem>.json (segments + words), <stem>.txt, <stem>.srt
"""
import json
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel


def fmt_ts(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def main():
    audio = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    model_name = sys.argv[3] if len(sys.argv) > 3 else "small"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = audio.stem

    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=8)
    segments, info = model.transcribe(
        str(audio),
        language="zh",
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        initial_prompt="以下是普通话播客对话，主题是AI对互联网产品经理和研发工程师的影响。",
    )

    t0 = time.time()
    result = []
    txt_lines = []
    srt_lines = []
    for i, seg in enumerate(segments, 1):
        words = [
            {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
            for w in (seg.words or [])
        ]
        item = {
            "id": i,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": words,
        }
        result.append(item)
        txt_lines.append(f"[{fmt_ts(seg.start)[:8]}] {item['text']}")
        srt_lines.append(f"{i}\n{fmt_ts(seg.start)} --> {fmt_ts(seg.end)}\n{item['text']}\n")
        if i % 25 == 0:
            print(f"{i} segs, audio {seg.end/60:.1f} min / {info.duration/60:.1f}, wall {time.time()-t0:.0f}s", flush=True)

    (out_dir / f"{stem}.json").write_text(
        json.dumps({"duration": info.duration, "segments": result}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (out_dir / f"{stem}.txt").write_text("\n".join(txt_lines), encoding="utf-8")
    (out_dir / f"{stem}.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    print("DONE", len(result), "segments", f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
