"""Render an edited podcast episode from an edit decision list (EDL).

Usage: python3 scripts/edit_episode.py edits/<episode>.json <out_dir>

Pipeline:
  1. explicit cuts from the EDL + shortening of long silences (detected on the audio itself)
  2. splice kept pieces in memory with 8 ms fades (mono), then highpass, light denoise, compression
  3. two-pass loudnorm to -16 LUFS / -1.5 dBTP
  4. export master .m4a (with chapters) and web .mp3, plus chapters.json and an edited transcript
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FADE = 0.008
SR = 48000


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def detect_silences(src, noise_db, min_gap):
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(src),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_gap}", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return list(zip(starts, ends))


def merge(ranges):
    ranges = sorted(r for r in ranges if r[1] > r[0])
    out = []
    for a, b in ranges:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def map_time(t, removals):
    """Raw time -> edited time. Times inside a removal snap to its end."""
    shift = 0.0
    for a, b in removals:
        if b <= t:
            shift += b - a
        elif a < t < b:
            return a - shift
        else:
            break
    return t - shift


def resolve_chapters(chapters, segments):
    flat, owners = "", []
    for s in segments:
        txt = s["text"].replace(" ", "")
        flat += txt
        owners += [s["start"]] * len(txt)
    out = []
    for ch in chapters:
        if "at" in ch:
            t = ch["at"]
        else:
            idx = flat.find(ch["find"].replace(" ", ""))
            if idx < 0:
                raise SystemExit(f"chapter text not found: {ch['find']}")
            t = owners[idx]
        out.append({"raw": t, "title": ch["title"]})
    return out


def fmt(t):
    t = max(t, 0)
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def main():
    edl_path = ROOT / sys.argv[1]
    out_dir = ROOT / sys.argv[2]
    out_dir.mkdir(parents=True, exist_ok=True)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    slug = edl["episode"]
    src = ROOT / edl["source"]
    tr = json.loads((ROOT / edl["transcript"]).read_text(encoding="utf-8"))
    duration = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(src)]).stdout.strip())

    sil = edl["silence"]
    side = sil["keep_each_side"]
    removals = [(c["start"], c["end"]) for c in edl["cuts"]]
    for a, b in detect_silences(src, sil["noise_db"], sil["min_gap"]):
        if b - a > 2 * side + 0.05:
            removals.append((a + side, b - side))
    removals = merge(removals)

    keeps, cur = [], 0.0
    for a, b in removals:
        if a - cur > 0.05:
            keeps.append((cur, a))
        cur = max(cur, b)
    if duration - cur > 0.05:
        keeps.append((cur, duration))

    pcm = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", str(SR),
         "-f", "f32le", "-"], check=True, capture_output=True).stdout
    audio = np.frombuffer(pcm, dtype=np.float32)
    n_fade = int(FADE * SR)
    ramp = np.linspace(0.0, 1.0, n_fade, dtype=np.float32)
    pieces = []
    for a, b in keeps:
        seg = audio[int(a * SR):int(b * SR)].copy()
        if len(seg) > 2 * n_fade:
            seg[:n_fade] *= ramp
            seg[-n_fade:] *= ramp[::-1]
        pieces.append(seg)
    spliced = np.concatenate(pieces)
    del audio, pcm

    stage = out_dir / "stage.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1",
         "-i", "-", "-af",
         "highpass=f=70,afftdn=nr=8:nf=-45,"
         "acompressor=threshold=-24dB:ratio=3:attack=15:release=250:makeup=2",
         "-c:a", "pcm_s16le", str(stage)],
        input=spliced.tobytes(), check=True, capture_output=True)

    measure = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(stage), "-af",
         "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    m = json.loads(measure[measure.rfind("{"):measure.rfind("}") + 1])
    ln = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
          f"offset={m['target_offset']}:linear=true")

    chapters = resolve_chapters(edl["chapters"], tr["segments"])
    edited_total = duration - sum(b - a for a, b in removals)
    for ch in chapters:
        ch["at"] = round(map_time(ch["raw"], removals), 2)
    for i, ch in enumerate(chapters):
        ch["end"] = chapters[i + 1]["at"] if i + 1 < len(chapters) else round(edited_total, 2)

    meta = [";FFMETADATA1", f"title=红豆牛奶不加糖 EP01｜AI 的变化", "artist=红豆牛奶不加糖"]
    for ch in chapters:
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(ch['at'] * 1000)}",
                 f"END={int(ch['end'] * 1000)}", f"title={ch['title']}"]
    meta_path = out_dir / "chapters.ffmeta"
    meta_path.write_text("\n".join(meta) + "\n", encoding="utf-8")

    master = out_dir / f"{slug}.m4a"
    web = out_dir / f"{slug}.mp3"
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(stage), "-i", str(meta_path),
         "-map_metadata", "1", "-map_chapters", "1", "-af", ln, "-ar", "48000",
         "-c:a", "aac", "-b:a", "128k", str(master)])
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(stage), "-i", str(meta_path),
         "-map_metadata", "1", "-map_chapters", "1", "-af", ln, "-ar", "44100",
         "-c:a", "libmp3lame", "-b:a", "64k", "-id3v2_version", "3", str(web)])

    removal_list = [(a, b) for a, b in removals]
    edited_segments = []
    for s in tr["segments"]:
        words = [w for w in s["words"]
                 if not any(a <= (w["start"] + w["end"]) / 2 < b for a, b in removal_list)]
        if not words:
            continue
        edited_segments.append({
            "start": round(map_time(words[0]["start"], removal_list), 2),
            "end": round(map_time(words[-1]["end"], removal_list), 2),
            "text": "".join(w["word"] for w in words).strip(),
        })

    (out_dir / "chapters.json").write_text(
        json.dumps([{"at": c["at"], "end": c["end"], "title": c["title"]} for c in chapters],
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "transcript.json").write_text(
        json.dumps(edited_segments, ensure_ascii=False, indent=0), encoding="utf-8")

    cut_explicit = sum(c["end"] - c["start"] for c in edl["cuts"])
    print(json.dumps({
        "raw_min": round(duration / 60, 2),
        "edited_min": round(edited_total / 60, 2),
        "explicit_cut_s": round(cut_explicit, 1),
        "silence_cut_s": round(duration - edited_total - cut_explicit, 1),
        "pieces": len(keeps),
        "chapters": [f"{fmt(c['at'])} {c['title']}" for c in chapters],
    }, ensure_ascii=False, indent=1))
    stage.unlink()


if __name__ == "__main__":
    main()
