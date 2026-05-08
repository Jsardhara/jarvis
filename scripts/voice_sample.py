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

# (sample_id, voice_name, engine, description, rate)
SAMPLES: list[tuple[str, str, str, str, str]] = [
    # Andrew variants — same voice, different speed
    ("01-andrew", "en-US-AndrewMultilingualNeural", "edge-tts",
     "Andrew — warm, neutral male, normal speed", "+0%"),
    ("01a-andrew-fast", "en-US-AndrewMultilingualNeural", "edge-tts",
     "Andrew +15% (faster)", "+15%"),
    ("01b-andrew-fastest", "en-US-AndrewMultilingualNeural", "edge-tts",
     "Andrew +25% (much faster)", "+25%"),
    ("01c-andrew-mono", "en-US-AndrewNeural", "edge-tts",
     "Andrew (non-multilingual variant) +10%", "+10%"),
    # Other warm male voices similar to Andrew
    ("07-eric", "en-US-EricNeural", "edge-tts",
     "Eric — warm mid-pitch male, like Andrew but younger, +10%", "+10%"),
    ("08-roger", "en-US-RogerNeural", "edge-tts",
     "Roger — deeper professional male, +10%", "+10%"),
    ("09-steffan", "en-US-SteffanNeural", "edge-tts",
     "Steffan — warm, conversational, +10%", "+10%"),
    ("10-guy", "en-US-GuyNeural", "edge-tts",
     "Guy — natural, calm male, +10%", "+10%"),
    # Originals kept for completeness
    ("02-brian", "en-US-BrianMultilingualNeural", "edge-tts",
     "Brian — deeper authoritative", "+0%"),
    ("03-christopher", "en-US-ChristopherNeural", "edge-tts",
     "Christopher — mid-pitch friendly", "+0%"),
    ("04-ryan-uk", "en-GB-RyanNeural", "edge-tts",
     "Ryan UK — British, most 'Jarvis'-y", "+0%"),
    ("05-piper-lessac", "en_US-lessac-medium", "piper",
     "Local Piper neural — free, slightly synthetic", "+0%"),
    ("06-sapi-default", "default", "sapi",
     "Windows SAPI — robotic baseline", "+0%"),
]

OUT_DIR = Path("state/voice_samples")


async def _gen_edge(voice: str, out_path: Path, rate: str = "+0%") -> None:
    from jarvis.voice.edge_tts_provider import EdgeTTSProvider  # type: ignore

    provider = EdgeTTSProvider(voice=voice, rate=rate)
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
    for sample_id, voice, engine, desc, rate in SAMPLES:
        ext = "mp3" if engine == "edge-tts" else "wav"
        out = OUT_DIR / f"{sample_id}.{ext}"
        try:
            if engine == "edge-tts":
                await _gen_edge(voice, out, rate=rate)
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
    _, voice, engine, _, rate = match
    env_path = Path(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    keep = [
        ln for ln in lines
        if not ln.startswith(("VOICE_NAME=", "VOICE_ENGINE_TTS=", "VOICE_RATE="))
    ]
    keep.append(f"VOICE_NAME={voice}")
    keep.append(f"VOICE_ENGINE_TTS={engine}")
    if rate != "+0%":
        keep.append(f"VOICE_RATE={rate}")
    env_path.write_text("\n".join(keep) + "\n")
    print(
        f"locked: VOICE_NAME={voice} VOICE_ENGINE_TTS={engine} VOICE_RATE={rate} in {env_path}"
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true", help="list samples and exit")
    p.add_argument("--select", help="lock in chosen sample id (writes .env)")
    args = p.parse_args()

    if args.list:
        for sample_id, voice, engine, desc, rate in SAMPLES:
            print(
                f"{sample_id:20} engine={engine:8} rate={rate:6} voice={voice:42}  # {desc}"
            )
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
