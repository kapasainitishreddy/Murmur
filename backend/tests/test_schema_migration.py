from sqlalchemy import create_engine

from app.schema_migration import migrate_murmur_table


def old_engine():
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        connection.exec_driver_sql(
            '''
            CREATE TABLE murmur (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              transcript TEXT NOT NULL,
              space TEXT NOT NULL,
              source TEXT NOT NULL,
              language TEXT,
              duration_seconds FLOAT,
              created_at DATETIME NOT NULL
            )
            '''
        )
        connection.exec_driver_sql(
            "INSERT INTO murmur (id,title,transcript,space,source,created_at) VALUES ('1','t','body','Memory','text','2026-09-07T04:00:00+00:00')"
        )
    return engine


def test_migration_adds_metadata_columns_and_preserves_existing_record():
    engine = old_engine()

    migrate_murmur_table(engine)

    with engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(murmur)').fetchall()}
        assert {'updated_at', 'tags_json', 'pinned'} <= columns
        row = connection.exec_driver_sql(
            'SELECT created_at, updated_at, tags_json, pinned FROM murmur WHERE id = ?',
            ('1',),
        ).one()
        assert row[1] == row[0]
        assert row[2] == '[]'
        assert row[3] in (0, False)


def test_migration_is_idempotent():
    engine = old_engine()
    migrate_murmur_table(engine)
    migrate_murmur_table(engine)

    with engine.connect() as connection:
        columns = [row[1] for row in connection.exec_driver_sql('PRAGMA table_info(murmur)').fetchall()]
        assert columns.count('updated_at') == 1
        assert columns.count('tags_json') == 1
        assert columns.count('pinned') == 1
