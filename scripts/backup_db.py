"""Back up the SHEFA SQLite database safely while the server is running.

    python scripts/backup_db.py [--db data/shefa.db] [--out backups] [--keep 14]

Uses SQLite's online backup API (a plain file copy of a WAL database can be torn),
writes `shefa-YYYYmmdd-HHMMSS.db`, and keeps only the newest `--keep` copies.
Run it from cron, e.g. `0 2 * * * cd /opt/shefa && python scripts/backup_db.py`.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path


def backup(db: Path, out: Path, keep: int) -> Path:
    if not db.exists():
        raise FileNotFoundError(f"No database at {db}")
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"shefa-{datetime.now():%Y%m%d-%H%M%S}.db"
    source = sqlite3.connect(str(db))
    destination = sqlite3.connect(str(target))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    for old in sorted(out.glob("shefa-*.db"))[:-keep]:
        old.unlink()
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path("data/shefa.db"))
    parser.add_argument("--out", type=Path, default=Path("backups"))
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()
    print(f"backed up to {backup(args.db, args.out, args.keep)}")


if __name__ == "__main__":
    main()
