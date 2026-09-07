from pathlib import Path


def test_transcribe_endpoint_uses_server_audio_policy():
    source = (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert "choose_audio_suffix" in source
    assert "AudioUploadError" in source
    assert "Path(audio.filename" not in source
    assert "status_code=415" in source
