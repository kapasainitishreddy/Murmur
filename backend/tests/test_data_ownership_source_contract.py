from pathlib import Path


def _source() -> str:
    return (Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8")


def test_json_backup_restore_and_erase_routes_exist():
    source = _source()
    assert '@app.get("/api/export.json")' in source
    assert '@app.post("/api/restore")' in source
    assert '@app.delete("/api/murmurs", status_code=204)' in source
    assert "build_backup" in source
    assert "validate_backup" in source


def test_restore_validates_before_mutating_database():
    source = _source()
    function = source[source.index("def restore_backup"):]
    validation = function.index("validate_backup")
    mutation = min(
        position for position in (
            function.find("session.delete("),
            function.find("session.add("),
        ) if position >= 0
    )
    assert validation < mutation


def test_murmur_edit_route_is_present():
    source = _source()
    assert '@app.patch("/api/murmurs/{murmur_id}"' in source
    assert "class MurmurUpdate" in source
