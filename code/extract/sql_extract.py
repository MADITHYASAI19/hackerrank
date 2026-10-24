"""SQL evidence extractor."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.loader import parse_ts

PREFIX_TO_SYSTEM = {
    "account_": "account_service",
    "analytics_": "analytics_platform",
    "audit_record_": "security_service",
    "backup_": "backup_service",
    "data_flow_": "integration_service",
    "export_": "export_service",
    "search_": "search_service",
    "support_": "support_platform",
    "tombstone_": "identity_service",
}

PREFIX_TO_CATEGORY = {
    "account_": "USER_PROFILE",
    "analytics_": "ANALYTICS_PROFILE",
    "audit_record_": "SECURITY_AUDIT_LOG",
    "backup_": "BACKUP_ARCHIVE",
    "data_flow_": "INTEGRATION_FLOW",
    "export_": "USER_EXPORT",
    "search_": "SEARCH_INDEX_ENTRY",
    "support_": "SUPPORT_MESSAGE",
    "tombstone_": "ACCOUNT_TOMBSTONE",
}


def extract_sql_evidence(file_path: Path, file_id: str, default_captured_at: Optional[datetime]) -> List[ExtractedRecord]:
    """Execute SQL script into in-memory sqlite3, inspect all tables, and yield ExtractedRecords."""
    records = []
    conn = sqlite3.connect(":memory:")
    try:
        content = file_path.read_text(encoding="utf-8")
        conn.executescript(content)
        cursor = conn.cursor()

        # Check snapshot_scope if present
        table_names = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        for tbl in table_names:
            if tbl == "snapshot_scope":
                continue
            cursor.execute(f"PRAGMA table_info({tbl})")
            columns = [c[1] for c in cursor.fetchall()]

            cursor.execute(f"SELECT * FROM {tbl}")
            rows = cursor.fetchall()
            for row in rows:
                row_dict = dict(zip(columns, row))
                res_id = row_dict.get("resource_id", "")
                if not res_id:
                    continue

                sys_id = "unknown_service"
                cat = "UNKNOWN"
                for p, s in PREFIX_TO_SYSTEM.items():
                    if res_id.startswith(p):
                        sys_id = s
                        cat = PREFIX_TO_CATEGORY.get(p, "UNKNOWN")
                        break

                captured_at = default_captured_at
                upd = parse_ts(str(row_dict.get("updated_at", "")))
                if upd:
                    captured_at = upd

                # Determine state_hint
                state_hint = "PRESENT"
                if "backup_restore_entries" in tbl:
                    # check restore_allowed
                    allowed = str(row_dict.get("restore_allowed", "")).lower()
                    if allowed in ("1", "true", "yes"):
                        state_hint = "ACTIVE"
                    else:
                        state_hint = "BLOCKED"
                elif "connector_subscriptions" in tbl:
                    enabled = str(row_dict.get("enabled", "")).lower()
                    if enabled in ("1", "true", "yes"):
                        state_hint = "ACTIVE"
                    else:
                        state_hint = "DISABLED"
                elif "customer_analytics_profiles" in tbl:
                    # Check if email/phone present vs null
                    has_id = bool(row_dict.get("email") or row_dict.get("phone") or row_dict.get("email_hash"))
                    state_hint = "PRESENT" if has_id else "ANONYMIZED"
                elif "customer_profiles" in tbl:
                    st = str(row_dict.get("account_status", "")).upper()
                    if st in ("DELETED", "PURGED"):
                        state_hint = "ABSENT"

                # Check if record_json is present and unpack it
                combined_identifiers = dict(row_dict)
                user_ref = str(row_dict.get("user_id") or row_dict.get("customer_reference") or row_dict.get("subject_reference") or "")
                
                if "record_json" in row_dict and row_dict["record_json"]:
                    try:
                        import json
                        nested = json.loads(str(row_dict["record_json"]))
                        if isinstance(nested, dict):
                            combined_identifiers.update(nested)
                            if not user_ref:
                                user_ref = str(nested.get("user_id") or nested.get("customer_reference") or nested.get("subject_reference") or "")
                            if "document" in nested and isinstance(nested["document"], dict):
                                combined_identifiers.update(nested["document"])
                                if not user_ref:
                                    user_ref = str(nested["document"].get("customer_reference") or nested["document"].get("user_id") or "")
                    except Exception:
                        pass

                records.append(
                    ExtractedRecord(
                        file_id=file_id,
                        captured_at=captured_at,
                        system_id=sys_id,
                        resource_id=res_id,
                        category=cat,
                        user_ref=user_ref,
                        identifiers=combined_identifiers,
                        state_hint=state_hint,
                        raw=row_dict,
                        source_table=tbl,
                    )
                )
    finally:
        conn.close()


    return records
