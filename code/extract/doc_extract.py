"""Document evidence extractor (PDF)."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.extract.sql_extract import PREFIX_TO_CATEGORY, PREFIX_TO_SYSTEM
from code.loader import parse_ts

try:
    import pypdf
except ImportError:
    pypdf = None


def extract_doc_evidence(file_path: Path, file_id: str, default_captured_at: Optional[datetime]) -> List[ExtractedRecord]:
    """Extract text from PDF documents using pypdf."""
    records = []
    text_content = ""
    if pypdf:
        try:
            reader = pypdf.PdfReader(str(file_path))
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text_content += t + "\n"
        except Exception:
            pass

    if not text_content:
        return records

    # Look for identifiers and resource references
    res_matches = re.findall(r"\b(account_\d+|support_\d+|export_\d+|audit_record_\d+|object_\d+)\b", text_content)
    emails = re.findall(r"[\w\.-]+@[\w\.-]+", text_content)
    user_ids = re.findall(r"\buser_\d+\b", text_content)

    found_resources = set(res_matches)
    if not found_resources:
        return records


    for res_id in found_resources:
        sys_id = "document_service"
        cat = "SUPPORT_ATTACHMENT"
        for p, s in PREFIX_TO_SYSTEM.items():
            if res_id.startswith(p):
                sys_id = s
                cat = PREFIX_TO_CATEGORY.get(p, "SUPPORT_ATTACHMENT")
                break

        records.append(
            ExtractedRecord(
                file_id=file_id,
                captured_at=default_captured_at,
                system_id=sys_id,
                resource_id=res_id,
                category=cat,
                user_ref=";".join(user_ids),
                identifiers={"emails": emails, "user_ids": user_ids, "text": text_content[:500]},
                state_hint="PRESENT",
                raw=text_content[:2000],
                source_table="pdf_document",
            )
        )

    return records
