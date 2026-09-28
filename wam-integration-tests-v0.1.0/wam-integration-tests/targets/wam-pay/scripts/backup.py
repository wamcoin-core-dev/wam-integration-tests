"""SQLite online backup. This does NOT back up the node wallet or its keys."""
import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file() or source == destination:
        raise ValueError("Choose an existing source and a different destination")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Source database integrity check failed")
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        try:
            dst = sqlite3.connect(destination)
            try:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed")
            finally:
                dst.close()
        except Exception:
            destination.unlink(missing_ok=True)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source"); parser.add_argument("destination")
    args = parser.parse_args()
    try:
        backup(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Backup failed ({type(exc).__name__}); no existing backup is overwritten.\n")
    print("Invoice database backup verified. Back up the node wallet separately.")


if __name__ == "__main__":
    main()
