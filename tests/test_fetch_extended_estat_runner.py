from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


def _load_runner_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_extended_estat.py"
    spec = importlib.util.spec_from_file_location("fetch_extended_estat_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_source_survives_executescript_transaction_reset() -> None:
    module = _load_runner_module()
    conn = sqlite3.connect(":memory:")

    def fetcher() -> int:
        # Schema helpers use executescript(), which implicitly commits and used
        # to invalidate the runner's outer SAVEPOINT.
        conn.executescript("CREATE TABLE IF NOT EXISTS sample(value INTEGER);")
        conn.execute("INSERT INTO sample(value) VALUES (1)")
        return 1

    count, error = module._run_source(conn, "sample", fetcher)

    assert count == 1
    assert error is None
    assert conn.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 1


def test_run_source_rolls_back_uncommitted_source_writes_on_failure() -> None:
    module = _load_runner_module()
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sample(value INTEGER)")
    conn.commit()

    def fetcher() -> int:
        conn.executescript("CREATE TABLE IF NOT EXISTS helper(value INTEGER);")
        conn.execute("INSERT INTO sample(value) VALUES (1)")
        raise ValueError("source failed")

    count, error = module._run_source(conn, "sample", fetcher)

    assert count == 0
    assert error == "ValueError: source failed"
    assert conn.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 0
