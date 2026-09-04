from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "cache" / "refresh-run.json"
DB_PATH = ROOT / "database" / "area_insights.db"
OUTPUT_PATH = ROOT / "web" / "data" / "refresh-status.json"
PHASES = ("prepare", "core", "station", "stats", "spatial", "build")
COUNT_TABLES = (
    "areas",
    "area_prices",
    "transactions",
    "population",
    "future_population",
    "facilities",
    "stations",
    "station_transactions",
    "area_scores",
    "geo_scores",
    "data_sources",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_init(args: argparse.Namespace) -> None:
    state = {
        "schema_version": 1,
        "run": {
            "run_id": str(args.run_id),
            "run_url": args.run_url,
            "scope": args.scope,
            "mode": args.mode,
            "from_year": args.from_year,
            "to_year": args.to_year,
            "cache_restored": args.cache_restored == "true",
            "started_at": now_iso(),
            "finished_at": None,
            "status": "running",
        },
        "phases": {name: {"status": "pending", "updated_at": None, "message": None} for name in PHASES},
    }
    state["phases"]["prepare"] = {"status": "success", "updated_at": now_iso(), "message": None}
    save_state(state)


def command_phase(args: argparse.Namespace) -> None:
    state = load_state()
    if not state:
        raise SystemExit("refresh state has not been initialized")
    state.setdefault("phases", {})[args.name] = {
        "status": args.status,
        "updated_at": now_iso(),
        "message": args.message or None,
    }
    save_state(state)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def source_family(dataset_id: str | None) -> str:
    value = (dataset_id or "unknown").strip()
    if not value:
        return "unknown"
    if ":" in value:
        return value.split(":", 1)[0]
    if "/" in value:
        return value.split("/", 1)[0]
    return value


def database_snapshot() -> dict:
    if not DB_PATH.exists():
        return {"available": False, "table_counts": {}, "latest_fetch_at": None, "source_families": []}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        counts: dict[str, int] = {}
        for table in COUNT_TABLES:
            if table_exists(conn, table):
                counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])

        latest_fetch_at = None
        families: dict[str, dict] = defaultdict(lambda: {"records": 0, "latest_fetched_at": None})
        if table_exists(conn, "data_sources"):
            rows = conn.execute("SELECT dataset_id, fetched_at FROM data_sources").fetchall()
            for row in rows:
                family = source_family(row["dataset_id"])
                item = families[family]
                item["records"] += 1
                fetched_at = row["fetched_at"]
                if fetched_at and (item["latest_fetched_at"] is None or fetched_at > item["latest_fetched_at"]):
                    item["latest_fetched_at"] = fetched_at
                if fetched_at and (latest_fetch_at is None or fetched_at > latest_fetch_at):
                    latest_fetch_at = fetched_at

        return {
            "available": True,
            "table_counts": counts,
            "latest_fetch_at": latest_fetch_at,
            "source_families": [
                {"family": family, **values}
                for family, values in sorted(families.items(), key=lambda item: item[0].lower())
            ],
        }
    finally:
        conn.close()


def command_export(_: argparse.Namespace) -> None:
    state = load_state()
    if not state:
        raise SystemExit("refresh state has not been initialized")

    phases = state.get("phases", {})
    statuses = [item.get("status") for item in phases.values()]
    if any(status == "failure" for status in statuses):
        overall = "failure"
    elif all(status in {"success", "skipped"} for status in statuses):
        overall = "success"
    else:
        overall = "running"

    state.setdefault("run", {})["status"] = overall
    state["run"]["finished_at"] = now_iso() if overall != "running" else None
    state["database"] = database_snapshot()
    state["generated_at"] = now_iso()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save_state(state)
    print(f"refresh status exported: {OUTPUT_PATH}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Track public-data refresh phases and export freshness metadata")
    sub = root.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--run-id", required=True)
    init.add_argument("--run-url", required=True)
    init.add_argument("--scope", required=True, choices=["all", "core", "station", "stats", "spatial", "build"])
    init.add_argument("--mode", required=True, choices=["incremental", "full"])
    init.add_argument("--from-year", type=int, required=True)
    init.add_argument("--to-year", type=int, required=True)
    init.add_argument("--cache-restored", choices=["true", "false"], required=True)
    init.set_defaults(func=command_init)

    phase = sub.add_parser("phase")
    phase.add_argument("--name", required=True, choices=PHASES)
    phase.add_argument("--status", required=True, choices=["pending", "running", "success", "skipped", "failure"])
    phase.add_argument("--message", default="")
    phase.set_defaults(func=command_phase)

    export = sub.add_parser("export")
    export.set_defaults(func=command_export)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
