from __future__ import annotations

from pathlib import Path

from japan_area_insights.site_deployment import deployment_errors

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def main() -> None:
    errors = deployment_errors(WEB)
    if errors:
        for error in errors:
            print(f"deployment configuration error: {error}")
        raise SystemExit(1)
    print("deployment configuration: ready")


if __name__ == "__main__":
    main()
