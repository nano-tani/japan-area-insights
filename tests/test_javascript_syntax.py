from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "web" / "recommend.js",
        ROOT / "web" / "station-search-results.js",
        ROOT / "web" / "station-decision.js",
        ROOT / "web" / "station-compare.js",
    ],
)
def test_interactive_search_javascript_has_valid_syntax(path: Path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    subprocess.run([node, "--check", str(path)], check=True, capture_output=True, text=True)
