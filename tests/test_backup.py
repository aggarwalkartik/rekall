import pytest
from pathlib import Path
from rekall.backup import create_backup
from rekall.storage import Storage
from rekall.schemas import Memory


@pytest.fixture
def db(tmp_path):
    storage = Storage(tmp_path / "test.db")
    storage.initialize()
    storage.add_memory(Memory(id="mem_001", content="Test", type="fact"))
    return storage, tmp_path / "test.db"


def test_backup_creates_file(db, tmp_path):
    storage, db_path = db
    backup_path = tmp_path / "backup.db"
    create_backup(db_path, backup_path)
    assert backup_path.exists()
    assert backup_path.stat().st_size > 0


def test_backup_contains_data(db, tmp_path):
    storage, db_path = db
    backup_path = tmp_path / "backup.db"
    create_backup(db_path, backup_path)
    backup_db = Storage(backup_path)
    backup_db.initialize()
    mem = backup_db.get_memory("mem_001")
    assert mem is not None
    assert mem.content == "Test"
    backup_db.close()
