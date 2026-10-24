"""Log evidence extractor."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.extract.sql_extract import PREFIX_TO_CATEGORY, PREFIX_TO_SYSTEM
from code.loader import parse_ts


def extract_log_evidence(file_path: Path, file_id: str, default_captured_at: Optional[datetime]) -> List[ExtractedRecord]:
    """Parse log files with key=value attributes."""
    records = []
    lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # Look for resource_id
        m_res = re.search(r'resource_id[=:]\s*["\']?([\w\d_]+)["\']?', line_clean)
        if not m_res:
            continue
        res_id = m_res.group(1)

        sys_id = "unknown_service"
        cat = "UNKNOWN"
        for p, s in PREFIX_TO_SYSTEM.items():
            if res_id.startswith(p):
                sys_id = s
                cat = PREFIX_TO_CATEGORY.get(p, "UNKNOWN")
                break

        # Parse timestamp from start of line
        m_time = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)", line_clean)
        log_time = parse_ts(m_time.group(1)) if m_time else default_captured_at

        # Derive state_hint
        state_hint = "PRESENT"
        if "rows=0" in line_clean or "404" in line_clean or "status=ABSENT" in line_clean or "deleted" in line_clean.lower():
            state_hint = "ABSENT"
        elif "enabled=false" in line_clean:
            state_hint = "DISABLED"
        elif "enabled=true" in line_clean:
            state_hint = "ACTIVE"
        elif "restore_allowed=false" in line_clean:
            state_hint = "BLOCKED"
        elif "restore_allowed=true" in line_clean:
            state_hint = "ACTIVE"
        elif "customer_email=null" in line_clean:
            state_hint = "ANONYMIZED"

        # Parse all key=value pairs
        pairs = re.findall(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|([^\s]+))', line_clean)
        log_attrs = {}
        for k, v1, v2, v3 in pairs:
            val = v1 or v2 or v3
            log_attrs[k] = val

        # Extract user_ref if present in attributes
        user_ref = str(
            log_attrs.get("subject_ref")
            or log_attrs.get("subject_reference")
            or log_attrs.get("lookup_key")
            or log_attrs.get("correlation_key")
            or log_attrs.get("customer_reference")
            or log_attrs.get("user_id")
            or ""
        )
        if not user_ref.startswith("user_"):
            # Check if any attribute value looks like a user_id
            for v in log_attrs.values():
                m_uid = re.search(r"\buser_\d+\b", str(v))
                if m_uid:
                    user_ref = m_uid.group(0)
                    break

        # Also store original line for regex fallback
        log_attrs["raw_log"] = line_clean

        records.append(
            ExtractedRecord(
                file_id=file_id,
                captured_at=log_time,
                system_id=sys_id,
                resource_id=res_id,
                category=cat,
                user_ref=user_ref,
                identifiers=log_attrs,
                state_hint=state_hint,
                raw=line_clean,
                source_table="log_file",
            )
        )

    return records

