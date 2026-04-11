# tests/test_server.py
import pytest
import json
from unittest.mock import patch, MagicMock
from rekall.server import create_app, AppContext
from rekall.storage import Storage
from rekall.embedder import Embedder


@pytest.fixture
def app_context(tmp_path):
    storage = Storage(tmp_path / "test.db")
    storage.initialize()
    embedder = Embedder()
    return AppContext(db=storage, embedder=embedder)


def test_create_app_returns_fastmcp():
    app = create_app()
    assert app.name == "rekall"


def test_app_has_recall_tool():
    app = create_app()
    tool_names = [t.name for t in app._tool_manager.list_tools()]
    assert "recall" in tool_names


def test_app_has_remember_tool():
    app = create_app()
    tool_names = [t.name for t in app._tool_manager.list_tools()]
    assert "remember" in tool_names


def test_app_has_forget_tool():
    app = create_app()
    tool_names = [t.name for t in app._tool_manager.list_tools()]
    assert "forget" in tool_names


def test_app_has_list_tool():
    app = create_app()
    tool_names = [t.name for t in app._tool_manager.list_tools()]
    assert "list_memories" in tool_names
