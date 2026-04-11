"""Hot backup for Rekall database."""
from __future__ import annotations
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def create_backup(source_path: Path, output_path: Path) -> None:
    """Create a hot backup of the database using sqlite3.backup()."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source_path))
    dst = sqlite3.connect(str(output_path))
    src.backup(dst)
    dst.close()
    src.close()


def main():
    """Entry point for rekall-backup."""
    import argparse
    parser = argparse.ArgumentParser(description="Backup Rekall database")
    parser.add_argument("--output", type=Path, help="Output path for backup")
    args = parser.parse_args()

    from rekall.config import get_config
    config = get_config()

    if not config.db_path.exists():
        print("No database found. Nothing to backup.", file=sys.stderr)
        return

    if args.output:
        output = args.output
    else:
        backup_dir = config.backups_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        output = backup_dir / f"rekall_{datetime.now():%Y%m%d_%H%M}.db"

    create_backup(config.db_path, output)
    print(f"Backup created: {output}", file=sys.stderr)


if __name__ == "__main__":
    main()
