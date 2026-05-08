"""Generate the same sentence in 6 voices for blind A/B selection.

Usage::

    # Generate samples (writes to state/voice_samples/*.mp3)
    python scripts/voice_sample.py

    # Lock in operator's choice (writes VOICE_NAME=<id> to .env)
    python scripts/voice_sample.py --select <voice_id>

    # List supported sample voices
    python scripts/voice_sample.py --list
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

SAMPLE_TEXT = (
    "Hey Jarvis here. Markets are quiet today, no trades pending. "
    "I'll let you know if anything changes."
)

# (sample_id, voice_name, engine, description)
SAMPLES: list[tuple[str, str, str, str]] = [
    ("01-andrew", "en-US-AndrewMultilingualNeural", "edge-tts",
     "Warm, neutral male — recommended Jarvis default"),
    ("02-brian", "en-US-BrianMultilingualNeural", "edge-tts",
     "Deeper authoritative male"),
    ("03-christopher", "en-US-ChristopherNeural", "edge-tts",
     "Mid-pitch friendly male"),
    ("04-ryan-uk", "en-GB-RyanNeural", "edge-tts",
     "British male — most 'Jarvis'-y"),
    ("05-piper-lessac", "en_US-lessac-medium", "piper",
     "Local Piper neural — slightly synthetic but free + offline"),
    ("06-sapi-default", "default", "sapi",
     "Windows SAPI default — robotic baseline"),
]

OUT_DIR = Path("state/voice_samples")


async def _gen_edge(voice: str, out_path: Path) -> None:
    from jarvis.voice.edge_tts_provider import EdgeTTSProvider  # type: ignore

    provider = EdgeTTSProvider(voice=voice)
    audio = await provider._synthesize_async(SAMPLE_TEXT)
    out_path.write_bytes(audio)


def _gen_piper(model: str, out_path: Path) -> None:
    import subprocess

    proc = subprocess.run(
        ["piper", "--model", model, "--output_file", str(out_path)],
        input=SAMPLE_TEXT.encode(),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"piper failed: {proc.stderr.decode(errors='replace')}")


def _gen_sapi(out_path: Path) -> None:
    try:
        import pyttsx3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "pyttsx3 not installed — pip install pyttsx3 (optional, only for SAPI sample)",
        ) from exc
    engine = pyttsx3.init()
    engine.save_to_file(SAMPLE_TEXT, str(out_path))
    engine.runAndWait()


async def generate_all() -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for sample_id, voice, engine, desc in SAMPLES:
        ext = "mp3" if engine == "edge-tts" else "wav"
        out = OUT_DIR / f"{sample_id}.{ext}"
        try:
            if engine == "edge-tts":
                await _gen_edge(voice, out)
            elif engine == "piper":
                _gen_piper(voice, out)
            elif engine == "sapi":
                _gen_sapi(out)
            print(f"[OK]  {sample_id} → {out}  ({desc})")
            written.append(out)
        except Exception as exc:  # noqa: BLE001
            print(f"[skip] {sample_id} ({engine}): {exc}", file=sys.stderr)
    return written


def lock_in_choice(sample_id: str) -> None:
    match = next((s for s in SAMPLES if s[0] == sample_id), None)
    if not match:
        raise SystemExit(f"unknown sample id: {sample_id}")
    _, voice, engine, _ = match
    env_path = Path(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    keep = [ln for ln in lines if not ln.startswith(("VOICE_NAME=", "VOICE_ENGINE_TTS="))]
    keep.append(f"VOICE_NAME={voice}")
    keep.append(f"VOICE_ENGINE_TTS={engine}")
    env_path.write_text("\n".join(keep) + "\n")
    print(f"locked: VOICE_NAME={voice} VOICE_ENGINE_TTS={engine} in {env_path}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true", help="list samples and exit")
    p.add_argument("--select", help="lock in chosen sample id (writes .env)")
    args = p.parse_args()

    if args.list:
        for sample_id, voice, engine, desc in SAMPLES:
            print(f"{sample_id:18} engine={engine:8} voice={voice:42}  # {desc}")
        return 0
    if args.select:
        lock_in_choice(args.select)
        return 0

    asyncio.run(generate_all())
    print()
    print("Play each file, pick a winner, then lock with:")
    print("  python scripts/voice_sample.py --select <id>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
