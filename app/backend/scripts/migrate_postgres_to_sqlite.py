"""Copy every Lab Builder table from a PostgreSQL database into a new SQLite file.

Used once to leave Docker: the old Postgres is restored from a backup into a temporary local
server, and this copies it table by table using the app's own models, then compares row counts.

    python scripts/migrate_postgres_to_sqlite.py <postgres-url> <sqlite-file>
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text

from app.core.database import Base
import app.models  # noqa: F401 - registers every table on Base.metadata


def _utc(value):
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def main(source_url: str, target_file: str) -> int:
    target = Path(target_file)
    if target.exists():
        print(f"{target} already exists; refusing to overwrite it.")
        return 1
    # Read every timestamp in UTC; SQLite keeps them without a zone, and the app reads them as UTC.
    source = create_engine(source_url, connect_args={"options": "-c timezone=UTC"})
    sink = create_engine(f"sqlite:///{target.as_posix()}")
    Base.metadata.create_all(sink)
    source_tables = set(inspect(source).get_table_names())
    known = {table.name for table in Base.metadata.sorted_tables}
    skipped = sorted(source_tables - known)
    problems = []
    with source.connect() as reader, sink.begin() as writer:
        for table in Base.metadata.sorted_tables:
            if table.name not in source_tables:
                print(f"{table.name}: not in the backup (new table), left empty")
                continue
            columns = {c["name"] for c in inspect(source).get_columns(table.name)}
            usable = [c for c in table.columns if c.name in columns]
            rows = [{key: _utc(value) for key, value in row._mapping.items()}
                    for row in reader.execute(select(*[table.c[c.name] for c in usable]))]
            if rows:
                writer.execute(table.insert(), rows)
            print(f"{table.name}: {len(rows)} rows")
    with source.connect() as reader, sink.connect() as check:
        for table in Base.metadata.sorted_tables:
            if table.name not in source_tables:
                continue
            a = reader.execute(text(f'select count(*) from "{table.name}"')).scalar()
            b = check.execute(text(f'select count(*) from "{table.name}"')).scalar()
            if a != b:
                problems.append(f"{table.name}: {a} in Postgres, {b} in SQLite")
    if skipped:
        print("Not copied (not part of the app's current tables):", ", ".join(skipped))
    if problems:
        print("COUNT MISMATCH:\n  " + "\n  ".join(problems))
        return 2
    print("All row counts match.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
