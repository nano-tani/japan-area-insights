from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "refresh-data.yml").read_text(encoding="utf-8")


def load_refresh_status_module():
    path = ROOT / "scripts" / "refresh_status.py"
    spec = importlib.util.spec_from_file_location("refresh_status_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refresh_workflow_is_split_into_resumable_phases():
    for job in ("prepare:", "core:", "station:", "stats:", "spatial:", "build:"):
        assert job in WORKFLOW
    assert "actions/upload-artifact@v4" in WORKFLOW
    assert "actions/download-artifact@v4" in WORKFLOW
    assert "refresh-db-core-${{ github.run_id }}" in WORKFLOW
    assert "refresh-db-spatial-${{ github.run_id }}" in WORKFLOW


def test_refresh_workflow_can_resume_from_a_previous_run_artifact_on_main():
    assert "resume_from_run_id" in WORKFLOW
    assert "resume_from_phase" in WORKFLOW
    assert "actions/github-script@v7" in WORKFLOW
    assert "listWorkflowRunArtifacts" in WORKFLOW
    assert "listJobsForWorkflowRun" in WORKFLOW
    assert "actions: read" in WORKFLOW
    assert "run-id: ${{ steps.resolve_resume.outputs.source_run_id }}" in WORKFLOW
    assert "resume requires scope=all" in WORKFLOW
    assert "source code ${run.head_sha || \"unknown\"} will not be checked out" in WORKFLOW
    assert "resume_phase == 'station'" in WORKFLOW
    assert "ref: ${{ github.sha }}" in WORKFLOW


def test_refresh_workflow_reuses_validated_db_and_defaults_to_incremental_automation():
    assert "actions/cache/restore@v4" in WORKFLOW
    assert "actions/cache/save@v4" in WORKFLOW
    assert "area-insights-db-${{ runner.os }}-main-" in WORKFLOW
    assert 'cron: "20 20 * * 0"' in WORKFLOW
    assert 'scope="core"' in WORKFLOW
    assert 'mode="incremental"' in WORKFLOW
    assert 'from_year="$((to_year - 1))"' in WORKFLOW
    assert "reusing cached future-population/facility/transport datasets" in WORKFLOW


def test_refresh_workflow_fails_safe_before_publishing():
    assert "validate_refresh_db.py --require-stations" in WORKFLOW
    assert "Refuse stale-code publication" in WORKFLOW
    assert 'current_main="$(git rev-parse origin/main)"' in WORKFLOW
    assert "Re-run with scope=build from the latest main" in WORKFLOW
    assert "continue-on-error: true" in WORKFLOW
    assert "refresh-diagnostics-${{ github.run_id }}" in WORKFLOW


def test_refresh_status_exports_phase_and_source_freshness(tmp_path):
    module = load_refresh_status_module()
    module.STATE_PATH = tmp_path / "cache" / "refresh-run.json"
    module.DB_PATH = tmp_path / "area_insights.db"
    module.OUTPUT_PATH = tmp_path / "web" / "refresh-status.json"

    conn = sqlite3.connect(module.DB_PATH)
    conn.execute("CREATE TABLE areas (area_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO areas(area_id) VALUES (?)", [(str(i),) for i in range(23)])
    conn.execute("CREATE TABLE data_sources (dataset_id TEXT, fetched_at TEXT)")
    conn.executemany(
        "INSERT INTO data_sources(dataset_id, fetched_at) VALUES (?, ?)",
        [
            ("XIT001:2026:13101:01", "2026-09-05T00:00:00+00:00"),
            ("XIT001:2026:13102:01", "2026-09-05T00:01:00+00:00"),
            ("XPT002:2026:13", "2026-09-05T00:02:00+00:00"),
        ],
    )
    conn.commit()
    conn.close()

    module.command_init(
        argparse.Namespace(
            run_id="123",
            run_url="https://example.invalid/run/123",
            scope="core",
            mode="incremental",
            from_year=2025,
            to_year=2026,
            cache_restored="true",
        )
    )
    for phase, status in (
        ("core", "success"),
        ("station", "skipped"),
        ("stats", "skipped"),
        ("spatial", "skipped"),
        ("build", "success"),
    ):
        module.command_phase(argparse.Namespace(name=phase, status=status, message=""))
    module.command_export(argparse.Namespace())

    payload = json.loads(module.OUTPUT_PATH.read_text(encoding="utf-8"))
    assert payload["run"]["status"] == "success"
    assert payload["run"]["cache_restored"] is True
    assert payload["database"]["table_counts"]["areas"] == 23
    families = {item["family"]: item for item in payload["database"]["source_families"]}
    assert families["XIT001"]["records"] == 2
    assert families["XPT002"]["latest_fetched_at"] == "2026-09-05T00:02:00+00:00"
