"""WP4 — Stateless Free-Infra tests (RED until backend.app.storage lands).

Spec: STORAGE_BACKEND=local|s3mock|r2; server.py OUT_DIR qua env; ledger
DATABASE_URL; mọi artifact ghi qua storage interface (stdlib-only HTTP).
"""
import inspect
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


# ---------------------------------------------------------------- T1: interface
def test_storage_interface_abc():
    from backend.app.storage.base import Storage

    assert inspect.isabstract(Storage)
    for method in ("save", "load", "exists", "delete"):
        assert hasattr(Storage, method), f"missing Storage.{method}"


# ---------------------------------------------------------------- T2: local
def test_local_disk_roundtrip(tmp_path):
    from backend.app.storage.local_disk import LocalDisk

    store = LocalDisk(root=str(tmp_path))
    store.save("a/b.txt", b"hello")
    assert store.exists("a/b.txt")
    assert store.load("a/b.txt") == b"hello"
    store.delete("a/b.txt")
    assert not store.exists("a/b.txt")


# ---------------------------------------------------------------- T3: s3mock
class _MockS3Handler(BaseHTTPRequestHandler):
    store: dict = {}

    def _key(self) -> str:
        return self.path.lstrip("/")

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", 0))
        self.store[self._key()] = self.rfile.read(length)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        body = self.store.get(self._key())
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200 if self._key() in self.store else 404)
        self.end_headers()

    def do_DELETE(self):
        self.store.pop(self._key(), None)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):  # silence
        pass


@pytest.fixture
def s3_endpoint():
    _MockS3Handler.store = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockS3Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_s3mock_roundtrip(s3_endpoint):
    from backend.app.storage.s3mock import S3MockStorage

    store = S3MockStorage(endpoint=s3_endpoint)
    store.save("x/y.bin", b"\x00\x01")
    assert store.exists("x/y.bin")
    assert store.load("x/y.bin") == b"\x00\x01"
    store.delete("x/y.bin")
    assert not store.exists("x/y.bin")


# ---------------------------------------------------------------- T4: factory
def test_factory_storage_backend(monkeypatch, tmp_path):
    from backend.app.storage.factory import get_storage
    from backend.app.storage.local_disk import LocalDisk
    from backend.app.storage.s3mock import S3MockStorage

    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out"))
    assert isinstance(get_storage(), LocalDisk)

    monkeypatch.setenv("STORAGE_BACKEND", "s3mock")
    monkeypatch.setenv("S3_ENDPOINT", "http://127.0.0.1:9999")
    backend = get_storage()
    assert isinstance(backend, S3MockStorage)
    assert backend.endpoint == "http://127.0.0.1:9999"

    monkeypatch.setenv("STORAGE_BACKEND", "r2")
    monkeypatch.setenv("R2_ENDPOINT", "https://acc.r2.cloudflarestorage.com/bucket")
    assert isinstance(get_storage(), S3MockStorage)

    monkeypatch.setenv("STORAGE_BACKEND", "bogus")
    with pytest.raises(ValueError):
        get_storage()


# ---------------------------------------------------------------- T5: server OUT_DIR
def test_server_out_dir_env_and_storage_write(monkeypatch, tmp_path):
    from backend.app.api import server as server_mod

    monkeypatch.setenv("OUT_DIR", str(tmp_path / "out2"))
    assert server_mod._out_dir() == tmp_path / "out2"

    calls = {}

    class SpyStorage:
        def save(self, key, data):
            calls[key] = data

    monkeypatch.setattr(server_mod, "get_storage", lambda: SpyStorage())
    server_mod._write_artifact("renders/x.mp4", b"abc")
    assert calls == {"renders/x.mp4": b"abc"}


# ---------------------------------------------------------------- T6: ledger DATABASE_URL
def test_ledger_database_url_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ledger.db'}")
    monkeypatch.delenv("LEDGER_DB_PATH", raising=False)
    from backend.app.cost.ledger import CostLedger

    ledger = CostLedger()
    assert ledger.db_path == str(tmp_path / "ledger.db")


# ---------------------------------------------------------------- T7: env example
def test_env_example_has_stateless_vars():
    with open(".env.example", encoding="utf-8") as f:
        text = f.read()
    for var in ("STORAGE_BACKEND", "R2_ENDPOINT", "DATABASE_URL", "OUT_DIR"):
        assert var in text, f".env.example missing {var}"
