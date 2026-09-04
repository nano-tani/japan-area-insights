# Public data refresh operations

`Refresh public data` is designed as a resumable pipeline rather than one long all-or-nothing job.

## Phases

| Scope | What it refreshes | Typical cadence |
| --- | --- | --- |
| `core` | ward transactions, land prices, population; annual/reference future population/facilities/transport are reused in incremental mode | weekly |
| `station` | station-area rebuild + station-code transaction history | monthly or when station market data changes |
| `stats` | extended e-Stat datasets + appraisal reports | monthly / after source releases |
| `spatial` | urban planning, hazard, evacuation/disaster, J-SHIS, GSI terrain | quarterly / after source releases |
| `build` | no external API fetch; validate DB, recompute scores, build JSON, run tests, publish | after code-only exporter/scoring changes |
| `all` | all phases in order | annual full refresh or recovery |

The scheduled run is `core + incremental` once a week (Sunday 20:20 UTC / Monday 05:20 JST).

## Incremental vs full

`incremental` restores the latest validated SQLite snapshot from GitHub Actions Cache. If year inputs are blank it refreshes the previous year through the current year. Stable annual/reference datasets (`future_population`, `facilities`, `stations`) are reused when present, which avoids downloading unchanged spatial reference data every week.

`full` refreshes the requested history range for the selected phases. Blank years mean the current year and five years back.

`rebuild_database=true` discards the cache and forces `all + full`. If no valid cache exists, any non-build run automatically falls back to `all + full`, preventing a partial database from replacing the public snapshot.

## Failure recovery

Each phase passes `database/area_insights.db` and `data/cache/refresh-run.json` to the next phase as a short-lived workflow artifact. A failed phase records its failure before the job exits, so the workflow view identifies the exact source group that failed.

For an API failure, dispatch a new run using only that scope, normally in `incremental` mode. Successful historical data remains in the cached DB and only the selected phase is fetched again.

The final build is fail-safe:

1. validate the DB contains 23 wards and required market/population/station data;
2. recompute ward/station scores and detailed analysis;
3. build public JSON;
4. run the full test suite;
5. save the validated DB cache;
6. verify `main` has not moved since the refresh started;
7. only then commit `web/data` to `main`.

If `main` changed while a long refresh was running, the data is **not** pushed using stale code. The validated DB is already cached, so rerun with `scope=build` from the latest `main`.

## Refresh status output

A successful publication includes `web/data/refresh-status.json` with:

- run ID / run URL;
- selected scope and mode;
- effective year range;
- whether a prior DB cache was restored;
- phase status (`success`, `skipped`, `failure`);
- table row counts;
- latest `data_sources.fetched_at` timestamp;
- source-family freshness (for example `XIT001`, `XPT002`).

This file is intended for an update-status UI and for operational checks without opening the SQLite DB.

## Recommended operation

Use weekly scheduled `core` refreshes as the normal path. Run `station` and `stats` after meaningful upstream releases, `spatial` when annual/periodic geographic sources change, and `all + full` only for annual rebuilds, schema recovery, or cache loss.

Avoid editing or merging code into `main` during a long `all` refresh when possible. If it happens, stale publication protection will stop the push rather than mix old code with newly generated data.
