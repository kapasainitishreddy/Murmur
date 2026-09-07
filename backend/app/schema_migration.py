from __future__ import annotations

from sqlalchemy.engine import Engine


def migrate_murmur_table(engine: Engine) -> None:
    """Add release metadata columns to an existing SQLite Murmur table.

    New databases already receive these fields through SQLModel metadata. Existing
    databases are upgraded additively and keep their original records.
    """
    if engine.dialect.name != 'sqlite':
        return

    with engine.begin() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if 'murmur' not in tables:
            return

        columns = {
            row[1]
            for row in connection.exec_driver_sql('PRAGMA table_info(murmur)').fetchall()
        }

        if 'updated_at' not in columns:
            connection.exec_driver_sql('ALTER TABLE murmur ADD COLUMN updated_at DATETIME')
            connection.exec_driver_sql(
                'UPDATE murmur SET updated_at = created_at WHERE updated_at IS NULL'
            )
        if 'tags_json' not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE murmur ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'"
            )
        if 'pinned' not in columns:
            connection.exec_driver_sql(
                'ALTER TABLE murmur ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT 0'
            )
