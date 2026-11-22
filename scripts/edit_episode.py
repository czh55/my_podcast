"""Render an edited podcast episode from an edit decision list (EDL).

Usage: python3 scripts/edit_episode.py edits/<episode>.json <out_dir> [--dry-run]

Two EDL shapes:
  - linear (原版): keep everything except explicit cuts and over-long silences; chapters by raw time / text
  - sections (精华版): ordered sections of clips located by text ("from" ... "to"), may reorder the
    raw timeline; a chime is inserted before every section with "chime": true
An EDL may set "base" to inherit source / transcript / glossary / cuts from another EDL.

Pipeline:
  1. explicit cuts + shortening of long silences (detected on the audio itself)
  2. splice kept pieces in memory with 8 ms fades (mono), then highpass, light denoise, compression
  3. two-pass loudnorm to -16 LUFS / -1.5 dBTP
  4. export master .m4a (with chapters) and web .mp3, plus chapters.json, an edited transcript and
     map.json (raw time -> edited time pieces, used by the web page to place timestamps)
--dry-run prints every clip with its duration and text, without rendering.
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
CLIP_PAD = (0.12, 0.30)
CHIME_GAP = 0.45


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def load_edl(path):
    edl = json.loads(Path(path).read_text(encoding="utf-8"))
    if "base" in edl:
        base = load_edl(ROOT / edl["base"])
        for key in ("source", "transcript", "glossary", "cuts", "silence"):
            edl.setdefault(key, base.get(key))
    return edl


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


def subtract(a, b, removals):
    """Parts of [a, b] not covered by removals."""
    out, cur = [], a
    for ra, rb in removals:
        if rb <= cur or ra >= b:
            continue
        if ra - cur > 0.05:
            out.append((cur, ra))
        cur = max(cur, rb)
    if b - cur > 0.05:
        out.append((cur, b))
    return out


class TextIndex:
    """Locate raw times by transcript text (spaces ignored)."""

    def __init__(self, segments):
        self.flat, self.owner = "", []
        self.words = [w for s in segments for w in s["words"]]
        for i, w in enumerate(self.words):
            txt = w["word"].replace(" ", "")
            self.flat += txt
            self.owner += [i] * len(txt)

    def find(self, text, after=0.0):
        key = text.replace(" ", "")
        idx = self.flat.find(key)
        while idx >= 0 and self.words[self.owner[idx]]["start"] < after:
            idx = self.flat.find(key, idx + 1)
        if idx < 0:
            raise SystemExit(f"text not found after {after:.1f}s: {text}")
        first, last = self.owner[idx], self.owner[idx + len(key) - 1]
        return self.words[first]["start"], self.words[last]["end"]

    def padded(self, a, b):
        """Extend [a, b] by CLIP_PAD without reaching into the neighbouring words."""
        prev_end = max((w["end"] for w in self.words if w["end"] <= a + 0.01), default=0.0)
        next_start = min((w["start"] for w in self.words if w["start"] >= b - 0.01), default=b + 9)
        return (max(a - CLIP_PAD[0], min(prev_end + 0.03, a), 0.0),
                min(b + CLIP_PAD[1], max(next_start - 0.03, b)))


def make_chime(level):
    """Two soft bell notes (E5 -> A5), about 1.3 s."""
    t = np.arange(int(1.3 * SR)) / SR
    out = np.zeros_like(t)
    for f, delay in ((659.25, 0.0), (880.0, 0.16)):
        tt = np.clip(t - delay, 0, None)
        env = np.where(t >= delay, np.exp(-tt / 0.32) * np.minimum(tt / 0.006, 1.0), 0.0)
        out += env * (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt)
                      + 0.08 * np.sin(6 * np.pi * f * tt))
    out *= level / np.abs(out).max()
    return out.astype(np.float32)


def fmt(t):
    t = max(t, 0)
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def main():
    edl_path = ROOT / sys.argv[1]
    out_dir = ROOT / sys.argv[2]
    dry = "--dry-run" in sys.argv
    edl = load_edl(edl_path)
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

    # plan: list of ("audio", raw_a, raw_b) / ("chime",) items, plus chapter marks before items
    plan, chapter_marks = [], []
    if "sections" in edl:
        index = TextIndex(tr["segments"])
        for sec in edl["sections"]:
            if sec.get("chime"):
                plan.append(("chime",))
            chapter_marks.append((len(plan), sec["title"]))
            if dry:
                print(f"== {sec['title']}")
            for clip in sec["clips"]:
                a, _ = index.find(clip["from"], clip.get("after", 0.0))
                _, b = index.find(clip["to"], a)
                a, b = index.padded(a, b)
                b = min(b, duration)
                kept = subtract(a, b, removals)
                if dry:
                    secs = sum(y - x for x, y in kept)
                    words = [w["word"] for s in tr["segments"] for w in s["words"]
                             if a <= (w["start"] + w["end"]) / 2 < b]
                    text = "".join(words).strip()
                    print(f"  [{fmt(a)}-{fmt(b)}] {secs:5.1f}s  {text[:40]} … {text[-30:]}")
                plan += [("audio", x, y) for x, y in kept]
    else:
        for x, y in subtract(0.0, duration, removals):
            plan.append(("audio", x, y))

    chime_len = 1.3 + 2 * CHIME_GAP
    n_chimes = sum(1 for p in plan if p[0] == "chime")
    edited_total = sum(p[2] - p[1] for p in plan if p[0] == "audio") + n_chimes * chime_len
    if dry:
        print(json.dumps({"edited_min": round(edited_total / 60, 2), "chimes": n_chimes}))
        return

    pcm = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", str(SR),
         "-f", "f32le", "-"], check=True, capture_output=True).stdout
    audio = np.frombuffer(pcm, dtype=np.float32)
    n_fade = int(FADE * SR)
    ramp = np.linspace(0.0, 1.0, n_fade, dtype=np.float32)
    chime = make_chime(0.5 * float(np.percentile(np.abs(audio), 99.9)))
    gap = np.zeros(int(CHIME_GAP * SR), dtype=np.float32)

    pieces, pmap, item_at, out_t = [], [], [], 0.0
    for item in plan:
        item_at.append(out_t)
        if item[0] == "chime":
            seg = np.concatenate([gap, chime, gap])
        else:
            _, a, b = item
            seg = audio[int(a * SR):int(b * SR)].copy()
            if len(seg) > 2 * n_fade:
                seg[:n_fade] *= ramp
                seg[-n_fade:] *= ramp[::-1]
            pmap.append((a, b, out_t))
        pieces.append(seg)
        out_t += len(seg) / SR
    edited_total = out_t
    spliced = np.concatenate(pieces)
    del audio, pcm

    stage = out_dir / "stage.wav"
    out_dir.mkdir(parents=True, exist_ok=True)
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

    def to_edited(t, snap=True):
        for a, b, o in pmap:
            if a <= t < b:
                return o + (t - a)
        if snap:
            later = [o for a, b, o in pmap if a >= t]
            return min(later) if later else edited_total
        return None

    if "sections" in edl:
        chapters = [{"at": round(item_at[i] + (chime_len if plan[i][0] == "chime" else 0), 2),
                     "title": title} for i, title in chapter_marks]
        chapters[0]["at"] = 0.0
    else:
        index = TextIndex(tr["segments"])
        chapters = []
        for ch in edl["chapters"]:
            raw = ch["at"] if "at" in ch else index.find(ch["find"])[0]
            chapters.append({"at": round(to_edited(raw), 2), "title": ch["title"]})
    for i, ch in enumerate(chapters):
        ch["end"] = chapters[i + 1]["at"] if i + 1 < len(chapters) else round(edited_total, 2)

    title = edl.get("title", "红豆牛奶不加糖 EP01｜AI 的变化")
    meta = [";FFMETADATA1", f"title={title}", "artist=红豆牛奶不加糖"]
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

    edited_segments = []
    for s in tr["segments"]:
        run_words, last = [], None
        for w in s["words"]:
            t = to_edited((w["start"] + w["end"]) / 2, snap=False)
            if t is None:
                continue
            if last is not None and (t < last or t - last > 3.0) and run_words:
                edited_segments.append(run_words)
                run_words = []
            run_words.append((t, w))
            last = t
        if run_words:
            edited_segments.append(run_words)
    edited_segments = sorted(
        ({"start": round(ws[0][0] - (ws[0][1]["end"] - ws[0][1]["start"]) / 2, 2),
          "end": round(ws[-1][0] + (ws[-1][1]["end"] - ws[-1][1]["start"]) / 2, 2),
          "text": "".join(w["word"] for _, w in ws).strip()} for ws in edited_segments),
        key=lambda s: s["start"])

    (out_dir / "chapters.json").write_text(
        json.dumps([{"at": c["at"], "end": c["end"], "title": c["title"]} for c in chapters],
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "transcript.json").write_text(
        json.dumps(edited_segments, ensure_ascii=False, indent=0), encoding="utf-8")
    (out_dir / "map.json").write_text(
        json.dumps([[round(a, 2), round(b, 2), round(o, 2)] for a, b, o in pmap]), encoding="utf-8")

    cut_explicit = sum(c["end"] - c["start"] for c in edl["cuts"]) if "sections" not in edl else 0
    print(json.dumps({
        "raw_min": round(duration / 60, 2),
        "edited_min": round(edited_total / 60, 2),
        "explicit_cut_s": round(cut_explicit, 1),
        "pieces": len(pmap),
        "chimes": n_chimes,
        "chapters": [f"{fmt(c['at'])} {c['title']}" for c in chapters],
    }, ensure_ascii=False, indent=1))
    stage.unlink()


if __name__ == "__main__":
    main()
