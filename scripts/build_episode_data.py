"""Build the web data (chapters + readable transcript) for an edited episode.

Usage: python3 scripts/build_episode_data.py edits/<episode>.json <render_dir>
Writes docs/episodes/data/<episode>.json (chapters, paragraphs, and the raw -> edited time map)
"""
import json
import sys
from pathlib import Path

from edit_episode import load_edl

ROOT = Path(__file__).resolve().parent.parent
MAX_PARA = 160
GAP = 1.0


def main():
    edl = load_edl(ROOT / sys.argv[1])
    render = ROOT / sys.argv[2]
    chapters = json.loads((render / "chapters.json").read_text(encoding="utf-8"))
    segs = json.loads((render / "transcript.json").read_text(encoding="utf-8"))
    pieces = json.loads((render / "map.json").read_text(encoding="utf-8"))
    glossary = sorted(edl.get("glossary", {}).items(), key=lambda kv: -len(kv[0]))

    def fix(text):
        for k, v in glossary:
            text = text.replace(k, v)
        return text

    paras, cur = [], None
    for s in segs:
        text = fix(s["text"]).replace(" ", "，")
        if cur and s["start"] - cur["end"] < GAP and len(cur["text"]) < MAX_PARA:
            cur["text"] += "，" + text
            cur["end"] = s["end"]
        else:
            if cur:
                paras.append(cur)
            cur = {"t": s["start"], "end": s["end"], "text": text}
    paras.append(cur)
    for p in paras:
        p["text"] = p["text"].rstrip("，") + "。"
        del p["end"]

    out = ROOT / "docs" / "episodes" / "data" / f"{edl['episode']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"chapters": chapters, "paragraphs": paras, "map": pieces}, ensure_ascii=False, indent=0),
                   encoding="utf-8")
    print(out.relative_to(ROOT), len(chapters), "chapters", len(paras), "paragraphs")


if __name__ == "__main__":
    main()
