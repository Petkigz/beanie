"""Voice — the mouth and ears (§11.6, row 49).

Traceability: ARCHITECTURE §11.6 (speaking uses the OS's own speech synthesis
— a limb built into every desktop platform; hearing needs a transcription
engine, and when none is installed Beanie says so plainly instead of faking
a transcript) and §9 (voice output is an action the same way opening a file
is: honest about whether it actually happened — ``spoken: False`` is a real
answer).

Speaking is opt-in (``BEANIE_VOICE=1``) and uses platform-native engines:
Windows SAPI via PowerShell, macOS ``say``, Linux ``espeak``/``spd-say``.
Hearing: if the optional ``faster-whisper`` (or ``speech_recognition``) package
is installed it is used on recordings; otherwise ``listen`` honestly reports
that the ear organ is present but unseated — and the WebUI's browser
speech-recognition (§11.7) is the live alternative everywhere Chrome/Edge
runs, no install required.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class VoiceResult:
    ok: bool
    why: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "why": self.why, "detail": self.detail}


class Voice:
    """One mouth on every platform; one ear when an engine is installed."""

    def __init__(self, *, enabled: Optional[bool] = None, dry_run: bool = False) -> None:
        self.enabled = enabled if enabled is not None else os.environ.get("BEANIE_VOICE") == "1"
        self.dry_run = dry_run

    # -- the mouth: speak ---------------------------------------------------

    def speaker(self) -> Optional[list[str]]:
        """The platform speech engine, as a command template, or None."""
        if sys.platform.startswith("win"):
            return ["powershell", "-NoProfile", "-Command",
                    "Add-Type -AssemblyName System.Speech; "
                    "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak([Console]::In.ReadToEnd())"]
        if sys.platform == "darwin":
            return ["say"]
        for tool in ("espeak", "spd-say"):
            if shutil.which(tool):
                return [tool]
        return None

    def speak(self, text: str) -> VoiceResult:
        if not self.enabled:
            return VoiceResult(False, "voice_off", "BEANIE_VOICE=1 enables the speaker")
        command = self.speaker()
        if command is None:
            return VoiceResult(False, "no_engine", "no speech engine found on this platform")
        if self.dry_run:
            return VoiceResult(True, "would_speak", f"would say {len(text)} characters")
        try:
            subprocess.run(command, input=text, text=True, timeout=30,
                           capture_output=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return VoiceResult(False, "engine_error", str(exc))
        return VoiceResult(True, "spoken", f"said {len(text)} characters aloud")

    # -- the ears: listen -----------------------------------------------------

    def transcription_engine(self) -> Optional[str]:
        """Name of an installed transcription engine, or None (the honest gap)."""
        for engine in ("faster_whisper", "speech_recognition"):
            try:
                __import__(engine)
                return engine
            except ImportError:
                continue
        return None

    def transcribe(self, audio_path: str) -> VoiceResult:
        """Turn a sound file into text — or honestly say the ear isn't seated."""
        engine = self.transcription_engine()
        if engine is None:
            return VoiceResult(
                False, "no_engine",
                "no transcription engine installed — the WebUI's browser speech "
                "recognition works with no install")
        try:
            if engine == "faster_whisper":
                from faster_whisper import WhisperModel  # type: ignore

                model = WhisperModel("base")
                segments, _info = model.transcribe(audio_path)
                return VoiceResult(True, "transcribed", " ".join(s.text for s in segments).strip())
            import speech_recognition as sr  # type: ignore

            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_path) as source:
                audio = recognizer.record(source)
            return VoiceResult(True, "transcribed", recognizer.recognize_whisper(audio))
        except Exception as exc:  # engine-specific failures, reported whole
            return VoiceResult(False, "engine_error", str(exc))
