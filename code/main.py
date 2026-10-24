"""Main entry point for Deletion Audit Agent."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.extract.registry import load_all_evidence
from code.identity import resolve_identity
from code.intent import classify_intent_offline
from code.loader import load_dataset, parse_ts
from code.planner import plan_case
from code.policy import evaluate_policy
from code.state import build_case_view
from code.usage import UsageLedger


def run_audit(
    requests_path: Path,
    output_path: Path,
    dataset_dir: Path,
    usage_report_path: Optional[Path] = None,
):
    print(f"Loading dataset from {dataset_dir}...")
    dataset = load_dataset(dataset_dir)

    print("Extracting evidence from all evidence files...")
    all_records = load_all_evidence(dataset, base_dir=dataset_dir.parent)
    print(f"Loaded {len(all_records)} evidence records.")

    # Read requests from target path
    with open(requests_path, "r", encoding="utf-8", newline="") as f:
        requests = list(csv.DictReader(f))

    print(f"Auditing {len(requests)} deletion requests...")
    usage = UsageLedger()

    output_rows = []
    for req in requests:
        cid = req.get("case_id", "")
        email = req.get("email", "")
        audit_at = parse_ts(req.get("audit_at", ""))
        req_text = req.get("request_text", "")

        # 1. Intent classification
        intent_res = classify_intent_offline(cid, req_text)

        if intent_res.intent == "NOT_DELETE":
            status, steps = plan_case(cid, "NOT_DELETE", [])
            output_rows.append({
                "case_id": cid,
                "deletion_status": status,
                "steps_json": json.dumps(steps, separators=(",", ":")),
            })
            continue

        # 2. Identity resolution
        ident = resolve_identity(email, dataset)
        if not ident:
            # Fallback if unresolvable
            status, steps = plan_case(cid, "DELETE", [])
            output_rows.append({
                "case_id": cid,
                "deletion_status": status,
                "steps_json": json.dumps(steps, separators=(",", ":")),
            })
            continue

        # 3. State reconstruction at audit_at
        case_view = build_case_view(ident, audit_at, all_records, dataset)

        # 4. Policy evaluation
        decisions = [evaluate_policy(res_state) for res_state in case_view.values()]

        # 5. Planning and sorting
        status, steps = plan_case(cid, "DELETE", decisions)

        output_rows.append({
            "case_id": cid,
            "deletion_status": status,
            "steps_json": json.dumps(steps, separators=(",", ":")),
        })

    # Sort output rows by case_id (lexical == numeric for 0-padded case_01..case_518)
    output_rows_sorted = sorted(
        output_rows,
        key=lambda r: int(r["case_id"].split("_")[1]) if "_" in r["case_id"] and r["case_id"].split("_")[1].isdigit() else r["case_id"],
    )

    # Write output.csv
    print(f"Writing {len(output_rows_sorted)} rows to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"], quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(output_rows_sorted)

    if usage_report_path:
        usage.generate_report(len(requests), usage_report_path)

    print("Audit run completed successfully.")


def main():
    parser = argparse.ArgumentParser(description="Ghost Data Still Exists - Deletion Audit Agent")
    parser.add_argument("--requests", type=Path, default=ROOT / "dataset" / "deletion_requests.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "output.csv")
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset")
    parser.add_argument("--usage-report", type=Path, default=ROOT / "code" / "evaluation" / "usage_report.md")
    parser.add_argument("--offline", action="store_true", default=True)

    args = parser.parse_args()
    run_audit(
        requests_path=args.requests,
        output_path=args.out,
        dataset_dir=args.dataset,
        usage_report_path=args.usage_report,
    )


if __name__ == "__main__":
    main()
