"""Neon routing for the project store: postgres DATABASE_URL selects the
psycopg backend; explicit file paths and empty env stay on SQLite."""
import backend.app.api.store as store


def test_db_backend_routes_postgres_url(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://u:p@host/db?sslmode=require"
    )
    assert store._db_backend() == "postgres"


def test_db_backend_explicit_path_stays_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://u:p@host/db?sslmode=require"
    )
    assert store._db_backend(str(tmp_path / "projects.db")) == "sqlite"


def test_db_backend_default_is_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert store._db_backend() == "sqlite"
