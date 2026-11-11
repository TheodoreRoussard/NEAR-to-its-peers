"""Offline build: data/raw/ -> data/processed/metrics.json.

Never reads the wall clock: the date comes from data/raw/MANIFEST.json ("as_of").
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class MissingSnapshot(Exception):
    """Raised when data/raw/ has no snapshot to build from."""


def build(raw_dir: Path, out_dir: Path) -> dict:
    manifest_path = raw_dir / "MANIFEST.json"
    if not manifest_path.exists():
        raise MissingSnapshot(
            f"No data snapshot at {manifest_path}. Run `make all` (needs network) to fetch one."
        )
    manifest = json.loads(manifest_path.read_text())
    metrics = {"as_of": manifest["as_of"]}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    return metrics


def main() -> int:
    try:
        build(ROOT / "data" / "raw", ROOT / "data" / "processed")
    except MissingSnapshot as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
