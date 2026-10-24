# PROMPTS.md: Step-by-step prompts with validation

How to use:
1. Start your AI coding tool from the **repo root** (so `AGENTS.md` logging to `log.txt` works).
2. Put `brain.md` in the repo root. Paste **Prompt 0** first, then one step prompt at a time.
3. Do not move to the next step until that step's **Validation** passes.

Rules that apply to every prompt (Prompt 0 sets them once):
- No hardcoded case ids, emails, labels or file names in logic. Everything derives from the data.
- Use only evidence captured at or before the case's `audit_at`.
- Never print real-looking personal data into logs; never write API keys to files.

---

## Prompt 0: Kickoff (paste once)

```text
Read ./AGENTS.md, ./problem_statement.md, ./README.md and ./brain.md fully before acting.
Follow AGENTS.md logging (append to ./log.txt each turn).

We are building the "Ghost Data Still Exists" deletion-audit agent in ./code/ (Python 3).
Architecture: deterministic core (loading, identity resolution, evidence extraction,
state reconstruction at audit_at, policy engine, planner/sorter) plus a small LLM role
for multilingual intent classification and a VLM/OCR role for PNG/PDF evidence.

Hard constraints:
- Output ./output.csv with header case_id,deletion_status,steps_json, 518 rows sorted by case_id.
- No hardcoded labels or case-specific answers. Fix rules, not cases.
- dataset/sample_output.csv is the only ground truth we have: use it for validation.
- Keep prompts in source or .md files. Reports go in code/evaluation/*.md.

Reply with: (1) your understanding of the task in 8 lines, (2) the list of the open
questions in brain.md section 9. Do not write code yet.
```

**Validation:** the answer mentions claims vs truth, `audit_at`, retention vs deletion, and the sort order. If not, re-paste `brain.md`.

---

## Prompt 1: Resolve the open questions (research scripts, no pipeline yet)

```text
Write throwaway scripts in ./code/scratch/ (not part of the final package) that answer
brain.md section 9 using dataset/ and the 32 sample cases. For each question print the
evidence and a one-line conclusion. Specifically:
1. Find how email_hash is computed (try sha256 of lowercase/trimmed email, etc.) and
   test against all rows of user_identities.csv.
2. For sample cases 05, 06, 07, 03, 04: list every resource id in sample_output.csv,
   its system_id, and which evidence file/row it came from.
3. Show how ids sort in the samples (string vs numeric) wherever two ids share a prefix.
4. Show one sample answer containing a tombstone/identity_service resource, and the
   evidence behind it.
5. List the tables/columns of every .sql file and the keys of every .json collection.
6. For every PNG and PDF, extract text (pdftotext / tesseract) and summarize which sample
   cases reference it in sample_output.csv.
Write conclusions to ./code/scratch/FINDINGS.md.
```

**Validation:**
- `email_hash` rule reproduces **100%** of `user_identities.csv` rows (or you document the exceptions).
- FINDINGS.md answers all 8 questions in `brain.md` §9, each with data, not guesses.
- Update `brain.md` §9 with the answers.

---

## Prompt 2: Loader and normalization (`code/loader.py`)

```text
Create code/loader.py.
- Load requests, sample requests, user_identities, user_audit_log, system_activity,
  deletion_rules, evidence_files, using the csv module (utf-8, newline='').
- Provide normalize_email(s): trim + lowercase. Provide parse_ts(s) returning an aware
  UTC datetime from ISO strings ending in Z.
- Build indexes: email->user rows, user_id->identity row, user_id->audit rows (sorted by
  event_time), resource_id->activity rows (sorted by event_time), file_id->evidence row.
- Pure functions, type hints, no global state besides an optional cached Dataset object.
Add tests in code/tests/test_loader.py.
```

**Validation:**
- Row counts: 518 requests, 32 samples, 850 identities, 306 audit rows, 4011 activities, 15 rules, 94 evidence files.
- Every request email (normalized) is found in `user_identities` **or** in the audit log's old/new email values. Report any miss (do not crash).
- `pytest code/tests` passes.

---

## Prompt 3: Intent classifier (`code/intent.py`, `code/prompts/intent.md`)

```text
Create code/intent.py and code/prompts/intent.md.
Goal: label each request_text as DELETE or NOT_DELETE.
Design:
- Prompt (in the .md file) instructs: label DELETE only if the person asks to erase/close
  account and personal data. NOT_DELETE for: update/correct info, change email/phone,
  marketing opt-out only, copy/export of data, "keep my account", login help, invoice copy,
  info request. Text may be English, Spanish, French, Portuguese, Japanese or Korean.
- Output strict JSON: {"case_id": "...", "intent": "DELETE|NOT_DELETE", "reason": "<=15 words"}.
- Batch up to 25 requests per call, temperature 0, retries on invalid JSON, disk cache
  keyed by hash(model+prompt+text).
- Provide a --offline fallback using multilingual keyword rules so the tests run without an API.
- Cross-check with system_activity CLASSIFY_REQUEST events (privacy_intake "non-deletion")
  as supporting evidence, but do not use them as the only source and never key on case ids.
- Track input/output tokens per call into a usage ledger (code/usage.py).
```

**Validation:**
- All 32 samples are DELETE (the samples have no non-deletion cases).
- Create `code/evaluation/custom_cases/intent_cases.json` with ≥ 20 hand-written texts (≥ 8 NOT_DELETE incl. at least 2 non-English, plus tricky ones like "close my account but keep order history"). Accuracy must be ≥ 95%; investigate every miss.
- Run on all 518: about 20 cases should be NOT_DELETE (the short English texts). Print them and eyeball each.
- Response JSON always parses; the cache makes a second run use **0** calls.

---

## Prompt 4: Identity resolver (`code/identity.py`)

```text
Create code/identity.py.
resolve_identity(email, audit_at) -> IdentitySet with:
 user_id, names, emails (current + historical), phones (current + historical),
 email_hashes (current + historical), and 'as_of' metadata.
Rules:
- Start from the user row matching the normalized email; if no current row matches,
  look for the email as an old_value/new_value in user_audit_log to find the user_id.
- Include old and new values from audit rows for that user_id (field email, phone, email_hash).
- Normalize emails; keep phone strings as-is plus a digits-only form for matching.
- Provide matches(text_or_record) -> list of (identifier_type, value) found in a record,
  checking emails (case-insensitive), hashes, phones (digits-only), and user_id.
- Do NOT match on names alone. Never fuzzy-match.
```

**Validation:**
- Every one of the 518 request emails resolves to exactly one `user_id`; list failures.
- A test on a user with an email change in the audit log returns both emails.
- A test that two different users with similar names (e.g. a name prefix) never collide.
- `matches()` finds the uppercase variant of an email.

---

## Prompt 5: Evidence extractors (`code/extract/`)

```text
Create code/extract/ with one module per format and a common schema.
Record (dataclass): file_id, captured_at, system_id, resource_id, category (from brain.md
prefix table), user_ref (user_id if present), identifiers (dict: emails, phones, hashes, names),
state_hint (PRESENT | ABSENT | REDACTED | ANONYMIZED | ACTIVE | DISABLED | BLOCKED | UNKNOWN),
raw (original row/line), source_table (for SQL: which table, e.g. *_primary vs *_replica).
Modules:
- sql_extract.py: load each .sql into in-memory sqlite3 (executescript); read ALL tables;
  keep primary/replica distinction; map tables to categories; capture snapshot_scope times.
- json_extract.py: parse snapshots[].records[] with their own captured_at.
- log_extract.py: parse key=value lines; derive state (rows=0/404 => ABSENT, enabled=false =>
  DISABLED, enabled=true => ACTIVE, customer_email=null => REDACTED/none).
- txt_extract.py: parse the pipe-delimited handover lines (NOT_FOUND => ABSENT,
  IDENTIFIABLE => PRESENT, ANONYMIZED, ACTIVE, BLOCKED).
- doc_extract.py: pdftotext first; if it returns < 50 chars use OCR; capture retention
  dates and legal-hold facts.
- image_extract.py: tesseract OCR first; if parsing fails or confidence is low, VLM call using
  code/prompts/image_extract.md (strict JSON schema below). Cache by file hash.
- registry.py: iterate evidence_files.csv, dispatch by extension, return all Records.
```

`code/prompts/image_extract.md` (runtime VLM prompt):

```text
You are reading a screenshot or scanned page from a company's internal console.
Extract every visible record as JSON. Output ONLY JSON, no commentary:
{"system": "<console name>", "captured_at": "<ISO or null>",
 "records": [{"resource_id": "...", "category": "...", "status": "...",
              "identifiers": {"emails": [], "phones": [], "user_ids": [], "names": []},
              "notes": "..."}]}
Copy values exactly as displayed. Do not guess unreadable text; use null.
```

**Validation:**
- Every `evidence_NN` in `evidence_files.csv` parses with **no exception**; print a table: file_id, format, #records, #unparsed lines.
- Total records > 0 for every file; investigate any file with 0.
- Spot-check 5 random records per format against the raw file (print side by side).
- Record counts by category are printed; every prefix in `brain.md` §4 appears at least once.
- For the 11 PNGs and 4 PDFs, a human checks the extraction against the image (open it).
- Re-running makes **0** VLM/OCR calls (cache).

---

## Prompt 6: State reconstruction at `audit_at` (`code/state.py`)

```text
Create code/state.py.
build_case_view(identity, audit_at, records, activities) -> list of ResourceState:
 resource_id, system_id, category, state (PRESENT|ABSENT|EXPOSED_PII|REDACTED|ANONYMIZED|
 ACTIVE|DISABLED|BLOCKED|RETAINED), exposing identifiers found, evidence_id (file_id or
 activity_id) that proves it, and a 'why' string.
Algorithm:
1. Candidate resources = records whose identifiers match the IdentitySet (any email/phone/hash/
   user_id, old or new) + resources linked by LINK_RESOURCE_IDENTITY activities to the user's
   email/user_id + resources named by the user's DELETE/SYNC/RESTORE activities.
2. For each candidate, take evidence captured <= audit_at; the latest one wins; for SQL, check
   primary AND each replica; any replica still holding it means PRESENT.
3. Activities up to audit_at are claims: use them to find candidates and to detect
   re-creation (e.g. SYNC_RECORD or RESTORE_BACKUP after a DELETE), not to prove absence.
4. Data flows: ACTIVE if the latest evidence/check says enabled/remains enabled; DISABLED otherwise.
5. Backups: restore risk if the latest evidence says restorable / ACTIVE; BLOCKED if blocked.
6. Emit the evidence id that is the strongest proof; be deterministic when several files agree
   (follow the pattern observed in FINDINGS.md).
```

**Validation:**
- Unit tests for each trap in `brain.md` §6 (replica drift, resurrection, old identifier, uppercase email, evidence after `audit_at` ignored).
- Run on the 32 samples: for each case compare the **set of (system_id, resource_id)** in your view with those in `sample_output.csv`. Print recall and precision of resources; target ≥ 95% before moving on.
- Any resource in the expected answer that you miss: print the file that contains it and why the matcher missed it.

---

## Prompt 7: Policy engine (`code/policy.py`)

```text
Create code/policy.py.
Load deletion_rules.csv at runtime; do not hardcode treatments beyond the category->prefix
mapping from brain.md. decide(resource_state, case_context) -> Decision with
 required_action (DELETE|REDACT|ANONYMIZE|RETAIN), compliant (bool), violation_type
 (REMAINING_RECORD | EXPOSED_PII | ACTIVE_DATA_FLOW | RESTORE_RISK | None), reason.
Rules:
- DELETE categories: any PRESENT record is REMAINING_RECORD.
- REDACT/ANONYMIZE categories: record may stay, but any exposing identifier =>
  EXPOSED_PII; fully redacted/anonymized => compliant.
- RETAIN (security audit within retention, active legal hold): must remain; compliant only if
  present and contains no identifiers beyond permitted ones; emit a PRESENT verification.
- Tombstone: user_id allowed; name/email/phone/email_hash not allowed.
- Backups: retained, but restore path must be BLOCKED; otherwise RESTORE_RISK.
- Data flows: any ACTIVE flow capable of copying the user's data => ACTIVE_DATA_FLOW.
- Support attachment: DELETE only if the catalog says it belongs only to the subject.
- Retention period / legal hold: read from the extracted docs and security_audit_records, not constants.
```

**Validation:**
- Table-driven unit tests: one per rule row (15 rules x compliant/violating).
- No decision ever returns DELETE for `audit_record_`, `legal_hold_`, or `backup_` categories.
- On the 32 samples: per-resource `required_action` matches the operation in `sample_output.csv` (DELETE_RECORD vs REDACT_RECORD vs ANONYMIZE_RECORD) at ≥ 95%.

---

## Prompt 8: Planner, sorter and writer (`code/planner.py`, `code/main.py`)

```text
Create code/planner.py and wire code/main.py.
plan_case(case, decisions) -> (status, steps):
- NOT_DELETE intent => ("NOT_APPLICABLE", []).
- No violations => "COMPLETE": VERIFICATION steps only (VERIFY_RECORD_ABSENT for deleted
  categories incl. the account, VERIFY_RECORD_PRESENT for retained, VERIFY_RECORD_ANONYMIZED /
  REDACTED for those categories, VERIFY_DATA_FLOW_DISABLED, VERIFY_RESTORE_BLOCKED), each with
  its evidence_id.
- Any violation => "INCOMPLETE": FINDING steps (evidence_id set), one REMEDIATION per finding
  (evidence_id ""), then VERIFICATION steps (evidence_id "") for every finding AND the
  standing checks seen in the samples (account absent, retained records present, etc.).
- Sorting: phase order, then operation order from problem_statement.md, then system_id,
  then resource_id (use the tie-break discovered in FINDINGS.md). Then number steps 1..N.
- States: use the exact state strings from the Allowed Operations table.
main.py: for every case in dataset/deletion_requests.csv, run the pipeline, write ./output.csv
using csv.writer (QUOTE_MINIMAL) and json.dumps(separators=(",", ":")); rows sorted by
case_id (decide whether case_id sorting is numeric or string by looking at sample_output.csv).
CLI: python3 code/main.py [--requests PATH] [--out PATH] [--offline].
```

**Validation:** write `code/validate_output.py` (also reused in Prompt 11) that fails loudly unless:
- header is exactly `case_id,deletion_status,steps_json`; row count equals the number of requests (518 for the real file);
- rows are sorted by `case_id` the same way as `sample_output.csv`;
- every `steps_json` parses; `step_no` is 1..N; keys are exactly the 7 allowed; `(phase, operation, state)` is in the allowed table;
- all invariants in `brain.md` §8.

Then run on the samples (`--requests dataset/sample_deletion_requests.csv --out /tmp/sample_pred.csv`) and make sure `validate_output.py` passes on both the prediction and `dataset/sample_output.csv`.

---

## Prompt 9: Evaluation harness (`code/evaluation/main.py`)

```text
Create code/evaluation/main.py. Inputs: --pred, --gold (default sample_output.csv).
Compute and print (and optionally write to Markdown):
- case-level status accuracy and a confusion matrix over COMPLETE/INCOMPLETE/NOT_APPLICABLE;
- step-level precision/recall/F1 on the tuple (phase, system_id, resource_id, operation, state);
- field-level accuracy over matched steps: each of phase, system_id, resource_id, operation,
  state, evidence_id (report separately; evidence_id is the hardest);
- sequence accuracy: exact-order match of the full array per case, and normalized edit distance;
- per-case diff for every case that is not an exact match: missing steps, extra steps,
  wrong evidence ids, ordering errors.
- Exit code 1 if status accuracy < threshold (flag --min-status-acc).
```

**Validation:**
- Gold vs gold gives 100% on everything (sanity test).
- A deliberately corrupted copy of gold (swap two steps, change a state, drop a case) shows exactly those errors.
- Output is deterministic.

---

## Prompt 10: Iterate on failures (repeat until stable)

```text
Run the pipeline on the 32 samples and the evaluation harness. For the 5 worst cases:
1. Show the diff, the evidence that explains the gold answer, and why our code differs.
2. Propose a GENERAL fix (rule, parser or matcher change), never a case-specific one.
3. Implement it, add a unit test, rerun the whole evaluation, and report the metric
   before/after. Reject the change if it hurts other cases.
Log each iteration (failure, root cause, fix, metrics) in code/evaluation/CHANGELOG.md; this
becomes the 'failures found and improvements made' section of the report.
```

**Validation:** metrics are non-decreasing across iterations; no fix contains a case id, email or file name literal (run `grep -rnE "case_[0-9]+|@[a-z]+\.(com|me)" code/ --include=*.py` and expect only tests/custom cases).

---

## Prompt 11: Your own evaluation cases (≥ 3, aim for 6)

```text
Create code/evaluation/custom_cases/ with small synthetic datasets (CSV + tiny SQL/JSON/log
evidence) and expected outputs, so the pipeline can run on them via --data-dir. Cases:
1. Non-deletion request in a language not in the dataset (e.g. German: "Bitte ändern Sie meine Telefonnummer") => NOT_APPLICABLE, [].
2. Orphan found only through an OLD email in the audit log => INCOMPLETE with REMAINING_RECORD.
3. Tombstone that still contains name/phone => EXPOSED_PII, REDACT, VERIFY_RECORD_REDACTED.
4. Clean deletion with security audit record retained => COMPLETE, verification only, includes VERIFY_RECORD_PRESENT.
5. Primary clean but failover replica still has the row => INCOMPLETE.
6. Delete reported SUCCESS but later RESTORE_BACKUP repopulated a search record => INCOMPLETE with RESTORE_RISK + search finding.
Run each, store pass/fail and diffs.
```

**Validation:** every custom case passes. Make the data synthetic (no real personal data). Keep the descriptions in `evaluation_report.md` as text.

---

## Prompt 12: Full run, usage ledger and output validation

```text
Run python3 code/main.py on dataset/deletion_requests.csv with a fresh usage ledger.
Then run code/validate_output.py on ./output.csv.
Write code/evaluation/usage_report.md from the ledger: provider(s), model name(s), number of
calls, input tokens, output tokens, total tokens, average tokens per request (divide by 518),
estimated cost total and per request with the price assumptions stated, per-model and overall
totals. If no LLM/VLM was used in the final run, state that explicitly with zeros.
```

**Validation:**
- `validate_output.py` passes: 518 rows, valid JSON, invariants OK.
- A second run produces a **byte-identical** `output.csv` (`sha256sum` both).
- Status distribution is printed and plausible: about 20 NOT_APPLICABLE; compare the rest with the sample distribution (22 INCOMPLETE / 10 COMPLETE) but do not force it.
- Randomly read 10 rows (3 COMPLETE, 5 INCOMPLETE, 2 NOT_APPLICABLE) by hand against the evidence.
- Usage numbers in the report equal the ledger totals.

---

## Prompt 13: Reports (`evaluation_report.md`) and README

```text
Write code/evaluation/evaluation_report.md with: (1) case-level status accuracy and
confusion matrix; (2) step-level and field-level accuracy; (3) sequence accuracy; (4) the
custom evaluation cases (description, expected, actual, pass/fail); (5) failures found and
improvements made (from CHANGELOG.md, with before/after metrics); (6) known limitations,
including anything uncertain on the 486 unlabeled cases. All numbers must be pasted from the
harness output, not estimated.
Write README.md at repo root (copied into code.zip) with: setup (python version, pip
requirements, tesseract/poppler install), env variables (no secrets), run commands for the
pipeline, evaluation and validation, architecture diagram (text), and where prompts live.
Create code/requirements.txt.
```

**Validation:**
- Every number in the report appears in the harness output or ledger.
- The README commands work from a clean clone (try in a fresh venv).
- `grep -rniE "sk-|api[_-]?key\s*=|secret" code README.md` finds no credentials.

---

## Prompt 14: Package and final check

```text
From the repo root, create code.zip with:
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store" "*/scratch/*"
Then list the zip contents and check each item in the README submission checklist.
```

**Validation checklist:**
- [ ] zip has `README.md`, `code/main.py`, `code/evaluation/evaluation_report.md`, `code/evaluation/usage_report.md`, prompts, requirements
- [ ] zip has **no** `dataset/`, no nested archives, no venv/caches, no keys
- [ ] root `output.csv` passes `validate_output.py`
- [ ] `log.txt` exists in the repo root and follows the `AGENTS.md` format
- [ ] reports are `.md` (the code judge ignores raw `.csv/.json/.sql/.log`)

---

## Prompt 15: Interview prep

```text
Generate 15 questions an AI judge could ask about this solution (architecture choices,
claims vs truth, audit_at handling, no-hardcoding evidence, LLM vs code split, evaluation
method, failures, cost, privacy) and draft a 3-sentence answer to each, citing real numbers
from our reports. Flag any answer where our evidence is weak.
```

**Validation:** every answer can be backed by a file in the repo. Practice each aloud once.

---

## Quick troubleshooting prompts

| Symptom | Prompt |
|---|---|
| Missing resources in a case | `For case X show every evidence record that mentions any identifier in the IdentitySet, and every activity linked to those resource ids; explain which ones state.py dropped and why.` |
| Wrong order | `Print our sorted step keys next to the gold keys for case X, and list the first position where they differ with the sort key tuples.` |
| Wrong evidence id | `For case X list every file that supports the finding for resource R, and show which one gold cites; infer the rule (earliest? latest <= audit_at? source type?) across 10 cases.` |
| False INCOMPLETE | `For case X list every finding and the exact evidence line that triggered it; check whether it was captured after audit_at.` |
