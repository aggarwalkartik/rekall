# tests/test_config.py
from rekall.config import get_config

def test_default_db_path():
    config = get_config()
    assert config.db_path.name == "rekall.db"
    assert ".rekall" in str(config.db_path)

def test_default_data_dir():
    config = get_config()
    assert config.data_dir.name == ".rekall"
