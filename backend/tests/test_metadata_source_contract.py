from pathlib import Path


def source() -> str:
    return (Path(__file__).parents[1] / 'app' / 'main.py').read_text(encoding='utf-8')


def test_model_persists_updated_at_tags_and_pinned_state():
    text = source()
    assert 'updated_at: datetime' in text
    assert 'tags_json: str' in text
    assert 'pinned: bool' in text
    assert 'migrate_murmur_table(engine)' in text


def test_api_exposes_and_updates_tags_and_pinned_state():
    text = source()
    assert 'tags: list[str]' in text
    assert 'pinned: bool' in text
    assert 'payload.tags' in text
    assert 'payload.pinned' in text
    assert 'deserialize_tags' in text
    assert 'serialize_tags' in text


def test_search_includes_tags_and_export_preserves_metadata():
    text = source()
    assert 'deserialize_tags(row.tags_json)' in text
    assert '"updated_at": murmur.updated_at.isoformat()' in text
    assert '"pinned": murmur.pinned' in text
