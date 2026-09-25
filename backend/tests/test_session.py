import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

from app.db import session as sess


def test_engine_disables_asyncpg_statement_cache_for_pgbouncer(monkeypatch) -> None:
    """PgBouncer in transaction mode breaks asyncpg's named prepared statements."""
    seen = {}

    def fake_engine(url, **kw):
        seen.update(kw)
        return object()

    monkeypatch.setattr(sess, "create_async_engine", fake_engine)
    monkeypatch.setattr(sess, "async_engine", None)
    monkeypatch.setattr(sess, "AsyncSessionLocal", None)
    monkeypatch.setattr(sess, "async_sessionmaker", lambda *a, **k: object())
    sess._bootstrap()
    args = seen["connect_args"]
    assert args["statement_cache_size"] == 0
    assert args["prepared_statement_name_func"]() != args["prepared_statement_name_func"]()
