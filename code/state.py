"""State reconstruction at audit_at."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set

from code.extract.schema import ExtractedRecord
from code.identity import IdentitySet
from code.loader import Dataset, parse_ts


@dataclass
class ResourceState:
    resource_id: str
    system_id: str
    category: str
    state: str  # PRESENT | ABSENT | REDACTED | ANONYMIZED | ACTIVE | DISABLED | BLOCKED
    exposing_identifiers: List[str] = field(default_factory=list)
    evidence_id: str = ""
    why: str = ""


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


def build_case_view(
    identity: IdentitySet,
    audit_at: Optional[datetime],
    all_records: List[ExtractedRecord],
    dataset: Dataset,
    requested_at: Optional[datetime] = None,
    reported_at: Optional[datetime] = None,
) -> Dict[str, ResourceState]:
    """Reconstruct state of all candidate resources for a user at audit_at."""
    # 1. Candidate resources:
    # - Catalog links in system_activity
    # - Direct identifier matches in records
    # - Activities mentioning user_id or emails
    # - Deletion worker events during request window
    candidate_res_ids: Set[str] = set()
    res_to_system: Dict[str, str] = {}
    res_to_category: Dict[str, str] = {}

    # Check catalog links and activities up to audit_at
    for act in dataset.system_activity:
        act_time = parse_ts(act.get("event_time"))
        if audit_at and act_time and act_time > audit_at:
            continue

        details = act.get("details", "")
        # Check if user matches
        matches = identity.matches(details)
        if matches:
            res_id = act.get("resource_id", "")
            if res_id:
                candidate_res_ids.add(res_id)

        # Deletion worker primary account submission in the request processing window
        if requested_at and act_time and requested_at <= act_time <= (reported_at or audit_at):
            if act.get("source_system") == "deletion_worker" and act.get("target_system") == "account_service":
                res_id = act.get("resource_id", "")
                if res_id:
                    candidate_res_ids.add(res_id)


    # Check extracted records up to audit_at
    matching_records_by_res: Dict[str, List[ExtractedRecord]] = {}
    for rec in all_records:
        if audit_at and rec.captured_at and rec.captured_at > audit_at:
            continue

        res_id = rec.resource_id
        is_candidate = res_id in candidate_res_ids

        if not is_candidate:
            matches = identity.matches(rec.identifiers)
            if not matches and rec.user_ref:
                matches = identity.matches(rec.user_ref)
            if matches:
                is_candidate = True
                candidate_res_ids.add(res_id)

        if is_candidate:
            if res_id not in matching_records_by_res:
                matching_records_by_res[res_id] = []
            matching_records_by_res[res_id].append(rec)

            if rec.system_id != "unknown_service":
                res_to_system[res_id] = rec.system_id
            if rec.category != "UNKNOWN":
                res_to_category[res_id] = rec.category

    # Build ResourceState for each candidate resource
    results: Dict[str, ResourceState] = {}

    for res_id in candidate_res_ids:
        # Determine system_id and category
        sys_id = res_to_system.get(res_id, "")
        cat = res_to_category.get(res_id, "")
        if not sys_id or not cat:
            for p, s in PREFIX_TO_SYSTEM.items():
                if res_id.startswith(p):
                    sys_id = sys_id or s
                    cat = cat or PREFIX_TO_CATEGORY.get(p, "UNKNOWN")
                    break

        recs = matching_records_by_res.get(res_id, [])
        # Sort records by captured_at descending (latest evidence wins)
        recs_sorted = sorted(
            recs,
            key=lambda r: r.captured_at or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo),
            reverse=True,
        )

        state = "PRESENT"
        best_evidence_id = ""
        why = ""

        if recs_sorted:
            latest = recs_sorted[0]
            best_evidence_id = latest.file_id
            state = latest.state_hint

            # If there are replica records, check for replication drift:
            # If any replica table holds the row present, state is PRESENT
            has_replica_present = any(
                "replica" in r.source_table and r.state_hint == "PRESENT"
                for r in recs_sorted
            )
            if has_replica_present and cat in ("USER_PROFILE", "SEARCH_INDEX_ENTRY"):
                state = "PRESENT"
                replica_rec = next(r for r in recs_sorted if "replica" in r.source_table and r.state_hint == "PRESENT")
                best_evidence_id = replica_rec.file_id
                why = "Replication drift: replica table retains record"

        # Check tombstone specifics
        if cat == "ACCOUNT_TOMBSTONE" or res_id.startswith("tombstone_"):
            # If identifiers (name, email, phone, hash) exist in raw, it's PRESENT (exposed PII)
            # If only user_id exists, it's REDACTED
            if recs_sorted:
                latest = recs_sorted[0]
                ident_matches = identity.matches(latest.identifiers)
                non_uid_matches = [m for m in ident_matches if m[0] != "user_id"]
                if non_uid_matches:
                    state = "PRESENT"
                    why = f"Tombstone exposes PII: {non_uid_matches}"
                else:
                    state = "REDACTED"
                    why = "Tombstone contains only stable user_id"

        # Check support message context
        if cat == "SUPPORT_MESSAGE" or res_id.startswith("support_"):
            if recs_sorted:
                latest = recs_sorted[0]
                ident_matches = identity.matches(latest.identifiers)
                if ident_matches:
                    state = "PRESENT"
                    why = "Support record exposes identifiers"
                else:
                    state = "REDACTED"

        # Check analytics profile
        if cat == "ANALYTICS_PROFILE" or res_id.startswith("analytics_"):
            if recs_sorted:
                latest = recs_sorted[0]
                ident_matches = identity.matches(latest.identifiers)
                if ident_matches:
                    state = "PRESENT"
                    why = "Analytics profile contains direct identifiers"
                else:
                    state = "ANONYMIZED"
                    why = "Analytics profile is anonymized"

        results[res_id] = ResourceState(
            resource_id=res_id,
            system_id=sys_id,
            category=cat,
            state=state,
            evidence_id=best_evidence_id,
            why=why,
        )

    return results
