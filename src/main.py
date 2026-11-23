from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

from .config import EXPECTED_FILES, REJECTED_DIR, REPORTS_DIR
from .extract import extract_drive, extract_local
from .load import load_all
from .transform import transform_all

LOG = logging.getLogger("randflow")


def run(source: str = "local", dry_run: bool = False) -> dict:
    LOG.info("Starting RandFlow ETL with source=%s dry_run=%s", source, dry_run)
    paths = extract_drive() if source == "drive" else extract_local()
    clean, rejects, report = transform_all(paths)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    for name in EXPECTED_FILES:
        # Write rejected rows for investigation (sensitive raw data: not for Git).
        reject_path = REJECTED_DIR / f"{name.removesuffix('.csv')}_rejected.csv"
        if name in rejects and not rejects[name].empty:
            rejects[name].to_csv(reject_path, index=False)
        else:
            reject_path.unlink(missing_ok=True)
        LOG.info("%s: raw=%d duplicates=%d clean=%d rejected=%d",
                 name, report[name]["raw_rows"],
                 report[name]["exact_duplicate_rows_dropped"],
                 report[name]["clean_rows"], report[name]["rejected_rows"])

    if dry_run:
        LOG.info("Dry run: skipped PostgreSQL loading")
        loaded = None
    else:
        loaded = load_all(clean)
        LOG.info("PostgreSQL staging loaded successfully: %s", loaded)

    result = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "dry_run": dry_run,
        "database_rows_loaded": loaded,
        "data_quality": report,
    }
    report_path = REPORTS_DIR / "quality_report.json"
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    LOG.info("Data quality report: %s", report_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="RandFlow financial ETL")
    parser.add_argument("--source", choices=["local", "drive"], default="local")
    parser.add_argument("--dry-run", action="store_true", help="Validate CSVs without database")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(source=args.source, dry_run=args.dry_run)


if __name__ == "__main__":
    main()