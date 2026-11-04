"""A spoken note about a job: Transcribe -> Muse reads the facts -> the card's needs change -> every robot is checked again.

  voice_note.py <job> <audio>        any audio or video file with sound
  voice_note.py <job> --text "..."   a typed note: skips Transcribe and says so

Writes outputs/jobs/<job>/card_voice.json and voice_note.json; card.json stays as it was.
"""
import argparse
import gc
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_job import check
from translator.card_writer import patch_needs, read_note
from translator.meta import transcribe
from translator.referee import Spend
from translator.robots import ROBOTS


def to_wav(audio, out):
    ffmpeg = shutil.which("ffmpeg") or str(ROOT / ".venv" / "bin" / "ffmpeg")
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(audio), "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
                    "-map_metadata", "-1", str(out)], check=True)


def hear(audio, spend):
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "note.wav"
        to_wav(audio, wav)
        spend.check(0.03)
        heard = transcribe(wav)
    spend.add(f"transcribe {Path(audio).name}", heard["cost_usd"])
    return heard


def flips(before, after):
    robots = [n for n in ROBOTS if not n.endswith("_muse")]
    rows = []
    for r in robots:
        a, b = check(r, before), check(r, after)
        gc.collect()
        rows.append({"robot": r, "before": a, "after": b, "flips": (a == "can try") != (b == "can try")})
        mark = "FLIPS" if rows[-1]["flips"] else "same "
        print(f"{mark} {r:10s} {a[:44]:44s} -> {b[:90]}", flush=True)
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("job", help="a folder name in outputs/jobs/")
    p.add_argument("audio", nargs="?")
    p.add_argument("--text", help="a typed note instead of audio")
    args = p.parse_args()
    if bool(args.audio) == bool(args.text):
        p.error("give an audio file or --text, not both")
    job = ROOT / "outputs" / "jobs" / args.job
    card = json.loads((job / "card.json").read_text())
    spend = Spend()

    heard = {"text": args.text, "seconds": 0, "cost_usd": 0.0} if args.text else hear(args.audio, spend)
    print(f"{'typed, no audio' if args.text else f'heard {heard["seconds"]:.1f} s, ${heard["cost_usd"]:.4f}'}: {heard['text']!r}")
    if not heard["text"].strip():
        print("nothing was said; the card stays as it is")
        return
    spend.check(0.01)
    note, cost = read_note(card, heard["text"])
    spend.add(f"muse note {args.job}", cost)
    print(f"Muse (${cost:.4f}): {json.dumps(note)}")

    new, changed = patch_needs(card, note, heard["text"])
    report = {"source": "typed" if args.text else str(args.audio), "transcript": heard["text"], "note": note, "changed": changed,
              "needs_before": card.get("needs"), "needs_after": new.get("needs"), "robots": [],
              "cost_usd": round(heard["cost_usd"] + cost, 5)}
    if not changed:
        print("no fact stated that changes the card; it stays as it is")
    else:
        print(f"needs changed: {changed}; guessed now: {new['needs'].get('guessed')}")
        (job / "card_voice.json").write_text(json.dumps(new, indent=1))
        report["robots"] = flips(card, new)
        print(f"{sum(r['flips'] for r in report['robots'])} of {len(report['robots'])} robots flip")
    (job / "voice_note.json").write_text(json.dumps(report, indent=1))
    print(f"cost ${report['cost_usd']:.4f}; all API spend so far ${spend.total:.3f}")


if __name__ == "__main__":
    main()
