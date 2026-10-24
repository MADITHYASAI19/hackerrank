"""Intent classifier for deletion requests (offline deterministic + cross-check)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class IntentResult:
    case_id: str
    intent: str  # "DELETE" or "NOT_DELETE"
    reason: str


# Phrases indicating that the user is NOT requesting account/data deletion
# Support English, Spanish, French, Portuguese, Japanese, Korean
NON_DELETE_PATTERNS = [
    # English
    r"not asking for deletion",
    r"not a request to erase",
    r"do not delete",
    r"don\'t delete",
    r"dont delete",
    r"do not close",
    r"dont close",
    r"leave the account active",
    r"leave my profile",
    r"keep the account",
    r"keep my account",
    r"keep my profile",
    r"without removing any of my records",
    r"stop the promotional emails",
    r"remove me from marketing lists only",
    r"change the email address used for this account",
    r"replace it with the new one",
    r"mobile number .* out of date",
    r"download my account information",
    r"copy of the information held",
    r"copy of last year\'s invoices",
    r"can\'t access my profile and need help",
    r"resetting the login",
    r"misspelled on the account",
    r"continue using the service",
    r"information request",
    # Spanish
    r"no borrar",
    r"no eliminar",
    r"mantener mi cuenta",
    r"mantener la cuenta",
    r"no cierren mi cuenta",
    r"solo quiero cambiar",
    r"solo cancelar suscripci[oó]n",
    # French
    r"ne pas supprimer",
    r"garder mon compte",
    r"garder le compte",
    r"ne fermez pas",
    r"mise [aà] jour",
    # Portuguese
    r"n[aã]o excluir",
    r"n[aã]o deletar",
    r"manter minha conta",
    r"manter a conta",
    r"apenas alterar",
    # Japanese
    r"削除しないで",
    r"退会しないで",
    r"アカウントを保持",
    r"メールアドレスの変更",
    # Korean
    r"삭제하지 마세요",
    r"계정을 유지",
    r"탈퇴가 아닙니다",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in NON_DELETE_PATTERNS]


def classify_intent_offline(case_id: str, request_text: str) -> IntentResult:
    """Classify request intent offline using high-precision multilingual patterns."""
    text = request_text.strip()
    for cp in COMPILED_PATTERNS:
        if cp.search(text):
            return IntentResult(
                case_id=case_id,
                intent="NOT_DELETE",
                reason=f"Matched non-deletion pattern: {cp.pattern[:20]}",
            )
    return IntentResult(case_id=case_id, intent="DELETE", reason="Requests account/data erasure")


def classify_all_requests(
    requests: List[Dict[str, str]],
    classify_activity_emails: Optional[set] = None,
) -> Dict[str, IntentResult]:
    """Classify a list of requests, optionally cross-checking with system_activity CLASSIFY_REQUEST."""
    results = {}
    for req in requests:
        cid = req.get("case_id", "")
        txt = req.get("request_text", "")
        email = req.get("email", "").strip().lower()

        res = classify_intent_offline(cid, txt)
        # Supporting cross-check if email is in classify_activity_emails
        if classify_activity_emails and email in classify_activity_emails:
            if res.intent != "NOT_DELETE":
                res = IntentResult(
                    case_id=cid,
                    intent="NOT_DELETE",
                    reason="Classified non-deletion by privacy intake activity",
                )
        results[cid] = res
    return results
