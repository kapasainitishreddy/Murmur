import pytest

from app.upload_policy import AudioUploadError, choose_audio_suffix, validate_audio_upload


def test_validate_audio_upload_accepts_browser_audio_types_and_codecs():
    assert validate_audio_upload('audio/webm;codecs=opus') == 'audio/webm'
    assert validate_audio_upload('audio/ogg') == 'audio/ogg'
    assert validate_audio_upload('audio/wav') == 'audio/wav'
    assert validate_audio_upload('audio/mpeg') == 'audio/mpeg'
    assert validate_audio_upload('audio/mp4') == 'audio/mp4'


def test_validate_audio_upload_rejects_non_audio_and_missing_types():
    for value in [None, '', 'image/png', 'text/plain', 'application/octet-stream']:
        with pytest.raises(AudioUploadError, match='Unsupported audio type'):
            validate_audio_upload(value)


def test_choose_audio_suffix_uses_server_mapping_not_filename():
    assert choose_audio_suffix('audio/webm', '../../payload.exe') == '.webm'
    assert choose_audio_suffix('audio/mpeg', 'voice.txt') == '.mp3'
    assert choose_audio_suffix('audio/mp4', 'voice.anything') == '.m4a'
