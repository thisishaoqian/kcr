"""Combine analysis JSON files into a CSV: python3 generate_database.py [directory]."""

import argparse
import csv
import json
import sys
from pathlib import Path


COLUMNS = [
    "date", "Lable", "plastic", "probe gas", "condition",
    "condition time(mins)", "weight(mg)", "bet_surface", "area(cm^2)", "flow rate", "uptake #", "desorb #",
]
METADATA_KEYS = [
    "experiment_date", "label", "plastic_name", "probe_gas_name", "condition",
    "condition_time", "material_weight", "bet_surface", "area", "flow_rate",
]


def read_row(path):
    """Read one experiment; unfinished phase results become empty CSV cells."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict):
        raise ValueError("missing metadata (older separate phase files are not supported)")
    metadata = data["metadata"]
    missing = [key for key in METADATA_KEYS if key not in metadata]
    if missing:
        raise ValueError(f"missing metadata fields: {', '.join(missing)}")
    phases = data.get("phases")
    if not isinstance(phases, dict):
        raise ValueError("missing or invalid phases object")
    row = [metadata[key] for key in METADATA_KEYS]
    for phase in ("uptake", "desorption"):
        selection = phases.get(phase, {})
        if not isinstance(selection, dict) or not isinstance(selection.get(phase, {}), dict):
            raise ValueError(f"invalid {phase} result")
        row.append(selection.get(phase, {}).get("molecules", ""))
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path.cwd(),
                        help="Directory containing JSON files (default: current directory)")
    parser.add_argument("--output", type=Path,
                        help="CSV path (default: database.csv in the input directory)")
    args = parser.parse_args(argv)
    if not args.directory.is_dir():
        parser.error(f"Not a directory: {args.directory}")
    output = args.output or args.directory / "database.csv"
    rows = []
    for path in sorted(args.directory.glob("*.json")):
        try:
            rows.append(read_row(path))
        except (OSError, ValueError) as error:
            print(f"Skipping {path.name}: {error}", file=sys.stderr)
    if not rows:
        parser.error("No supported analysis JSON files found; CSV was not written.")
    try:
        with output.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(COLUMNS)
            writer.writerows(rows)
    except OSError as error:
        parser.error(f"Cannot write {output}: {error}")
    print(f"Saved {len(rows)} experiments to {output.resolve()}")


if __name__ == "__main__":
    main()
