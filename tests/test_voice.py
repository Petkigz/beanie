"""Voice — mouth and ears (§11.6, row 49).

The mouth speaks through the platform's own engine when the owner opts in, and
says *would speak* in dry-run — never "I said it" without making a sound. The
ears are honest about the biggest gap in computing: when no transcription
engine is installed, "I cannot hear yet" is the answer, not a fabricated
transcript.
"""

from __future__ import annotations

from beanie.voice import Voice


def test_voice_off_is_not_silent_deception():
    voice = Voice(enabled=False, dry_run=True)
    result = voice.speak("hello there")
    assert result.ok is False and result.why == "voice_off"


def test_dry_run_reports_would_speak_with_platform():
    voice = Voice(enabled=True, dry_run=True)
    result = voice.speak("playing your song now")
    if voice.speaker() is None:          # platform without an engine → honest too
        assert result.why == "no_engine"
    else:
        assert result.ok and result.why == "would_speak"
        assert "21 characters" in result.detail


def test_missing_transcription_engine_is_an_honest_gap():
    voice = Voice(enabled=True)
    engine = voice.transcription_engine()
    result = voice.transcribe("/tmp/recording.wav")
    if engine is None:
        assert result.ok is False and result.why == "no_engine"
        assert "WebUI" in result.detail  # points at the zero-install alternative
    else:
        pass  # an installed engine is exercised only against real audio


def test_speaker_command_per_platform(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    assert Voice().speaker() == ["say"]
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/espeak" if name == "espeak" else None)
    assert Voice().speaker() == ["espeak"]
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert Voice().speaker() is None
