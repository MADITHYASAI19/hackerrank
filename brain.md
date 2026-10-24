# brain.md: Understand the Whole Project in 10 Minutes

Read this before touching code. It is the mental model. `PROMPTS.md` is the execution plan.

Legend: **[V]** = verified in the dataset while reading. **[?]** = a hypothesis you must verify on the data.

---

## 1. The one-sentence job

For each request, work out whether the person's data is **truly** gone at `audit_at`, and emit an **ordered, evidence-cited list of findings, fixes and checks** in a strict JSON format.

## 2. The core idea: claims vs. truth

| Source | Treat as |
|---|---|
| `reported_status` in the request | A claim. Never trust it |
| `system_activity.csv` `reported_result` (SUCCESS/FAILED/PARTIAL) | A claim. A SUCCESS delete can be undone by a later sync |
| Evidence files (SQL, JSON, logs, txt, PDF, PNG) | The truth, as of each file's `captured_at` |
| `deletion_rules.csv` | The law: what must happen to each category |

**Truth at `audit_at`** means: for each resource, use the **latest evidence captured at or before `audit_at`**. Evidence captured after `audit_at` must not be used to decide state.

## 3. The pipeline (mental picture)

```
request ──► is it a deletion request? ──no──► NOT_APPLICABLE, []
              │ yes
              ▼
        who is this person? (user_id + every email/phone/hash, past and present)
              ▼
        which resources belong to them? (resource ids, via evidence + catalog links)
              ▼
        what is each resource's state at audit_at?
              ▼
        what does the rule for its category require? (DELETE/REDACT/ANONYMIZE/RETAIN)
              ▼
        violation? active flow? restore path?  ──► INCOMPLETE (findings + fixes + checks)
        none of the above                      ──► COMPLETE   (verification steps only)
              ▼
        sort steps by the fixed order, number them, write the CSV
```

## 4. Data map **[V]**

### Resource-id prefixes (from `system_activity.csv`)

| Prefix | System / category | Rule |
|---|---|---|
| `account_` | account_service, USER_PROFILE | DELETE |
| `tombstone_` | identity_service, ACCOUNT_TOMBSTONE | REDACT (keep `user_id` only) |
| `search_` | search_service, SEARCH_INDEX_ENTRY | DELETE |
| `cache_` | cache_service, CACHE_ENTRY | DELETE |
| `support_` | support_platform, SUPPORT_MESSAGE | REDACT (shared context) |
| `object_` | object_storage, SUPPORT_ATTACHMENT | DELETE if it belongs only to the subject |
| `analytics_` | analytics_platform, ANALYTICS_PROFILE | ANONYMIZE |
| `export_` | export_service, USER_EXPORT | DELETE |
| `marketing_` | marketing_platform, MARKETING_PROFILE | DELETE |
| `email_delivery_` | email_delivery_service, EMAIL_DELIVERY_LOG | REDACT |
| `audit_record_` | security_service, SECURITY_AUDIT_LOG | RETAIN within the retention period |
| `legal_hold_` | legal_service, LEGAL_HOLD_RECORD | RETAIN while the hold is active |
| `backup_` | backup_service, BACKUP_ARCHIVE | RETAIN, but restore must be blocked |
| `data_flow_` | integration_service (connectors and syncs) | Not data; a process. Must be DISABLED |

Product telemetry and secondary identifiers appear in `deletion_rules.csv` but have no dedicated prefix in the activity log **[?]**. Look for them in the evidence tables.

### Identity data **[V]**
- `user_identities.csv`: current `user_id, name, email, phone, email_hash`.
- `user_audit_log.csv`: `field_name` is only `email`, `email_hash` or `phone`, each with `old_value` and `new_value`. So a leftover record may carry an **old** email, hash or phone.
- Emails appear in different cases in evidence (e.g. `CHOI.JIHOON94@GMAIL.COM`). Normalize before matching.
- `email_hash` is a 64-hex string (SHA-256 style). Its relation to the email (hashing method, case) must be confirmed by computing it **[?]**.

### Catalog links **[V]**
`system_activity.csv` has `LINK_RESOURCE_IDENTITY` events from `data_catalog`:
> "Data catalog linked search_428 (search_428) to g.silva76@gmail.com and user_13."

This ties **resource ids to an email and user_id**. It is the main way to know which resource belongs to whom when the evidence row itself doesn't say. For attachments the wording is "belongs only to X"; that decides whether the SUPPORT_ATTACHMENT rule applies (delete only if it belongs only to the subject).

### Activity details that carry state **[V]**
| Event | Details text means |
|---|---|
| `CHECK_DATA_FLOW` | "...confirmed that data flow X **remains enabled**" (active flow) |
| `CHECK_RESTORE_ACCESS` | "...archive X **can still be restored**" (restore risk) |
| `RESTORE_BACKUP` | "Restore job **repopulated downstream resource** search_NNNN" (data was recreated) |
| `CLASSIFY_REQUEST` | "...classified request for X as **non-deletion**; no destructive action was authorized" |
| `DELETE_RECORD` + FAILED/PARTIAL | Delete did not fully happen |
| `SYNC_RECORD` after a delete | Possible recreation (check the evidence) |

### Evidence formats
| Format | Content | How to read it |
|---|---|---|
| `.sql` | SQLite snapshots. Tables like `customer_profiles`, `customer_search_documents`, `customer_analytics_profiles`, `support_records`, `customer_exports`, `connector_subscriptions`, `backup_restore_entries`, `security_audit_records`, plus a `snapshot_scope` table **[V]** | Load into in-memory SQLite. Some files hold `_primary` and `_replica` tables to compare for drift |
| `.json` | `snapshots[].{captured_at, data_store, collection, records[]}` **[V]** | Parse. Note per-snapshot `captured_at` is separate from the file's `captured_at` |
| `.log` | `key=value` lines: `resource_id=… rows=0 http_status=404`, `enabled=false`, `customer_email=null` **[V]** | Regex. `rows=0` or 404 means absent; `enabled=false` means flow disabled |
| `.txt` | Pipe lines: `time \| system \| resource \| CATEGORY \| STATE \| identifier` with states like `NOT_FOUND`, `IDENTIFIABLE`, `ANONYMIZED`, `ACTIVE`, `BLOCKED` **[V]** | Split on `\|` |
| `.pdf` | Compliance journal with retention info ("retain until 25 Aug 2027") **[V]** | `pdftotext`; OCR/VLM fallback |
| `.png` | Console screenshots **[?]** | OCR or a VLM |

## 5. Decision rules

### Status
- `NOT_APPLICABLE`: the person did not ask for deletion. Output is exactly `[]`.
- `INCOMPLETE`: at least one of: a record that should be deleted still exists; a record that should be redacted/anonymized still exposes identifiers; a retained record carries an identifier it shouldn't; an active data flow; a restore path.
- `COMPLETE`: none of the above, **and** retained records still exist.

### Required completion conditions (from the statement)
1. Every relevant copy has the treatment the rules require.
2. No active sync, import or restore path can recreate the data.
3. Retained records contain only permitted identifiers.
4. Records that must be retained are still available.

### Finding to fix to check mapping **[V from samples]**
| Finding | Fix | Check |
|---|---|---|
| REPORT_REMAINING_RECORD / PRESENT | DELETE_RECORD / ABSENT | VERIFY_RECORD_ABSENT / ABSENT |
| REPORT_EXPOSED_PII / PRESENT | REDACT_RECORD / REDACTED or ANONYMIZE_RECORD / ANONYMIZED | VERIFY_RECORD_REDACTED or VERIFY_RECORD_ANONYMIZED |
| REPORT_ACTIVE_DATA_FLOW / ACTIVE | DISABLE_DATA_FLOW / DISABLED | VERIFY_DATA_FLOW_DISABLED / DISABLED |
| REPORT_RESTORE_RISK / ACTIVE | BLOCK_RESTORE / BLOCKED | VERIFY_RESTORE_BLOCKED / BLOCKED |
| none (retained and fine) | none | VERIFY_RECORD_PRESENT / PRESENT |

Observed in the samples:
- Support records with exposed PII get REDACT; analytics profiles get ANONYMIZE; the account profile gets DELETE.
- Even INCOMPLETE cases end with `VERIFY_RECORD_ABSENT` for the account (`case_06`: search finding, search delete, then verify account absent and search absent).
- Security audit records only ever appear as `VERIFY_RECORD_PRESENT`.

### Steps by case type
| Type | Phases | `evidence_id` |
|---|---|---|
| COMPLETE | VERIFICATION only | Real id on every step |
| INCOMPLETE | FINDING + REMEDIATION + VERIFICATION | Findings: real id. Remediation and verification: `""` |
| NOT_APPLICABLE | none, `[]` | n/a |

### Sorting (exact)
1. Phase: FINDING, REMEDIATION, VERIFICATION.
2. Within a phase, operation order:
   - FINDING: REPORT_REMAINING_RECORD, REPORT_EXPOSED_PII, REPORT_ACTIVE_DATA_FLOW, REPORT_RESTORE_RISK.
   - REMEDIATION: DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE_RECORD, REDACT_RECORD, ANONYMIZE_RECORD.
   - VERIFICATION: VERIFY_RECORD_ABSENT, VERIFY_RECORD_PRESENT, VERIFY_RECORD_REDACTED, VERIFY_RECORD_ANONYMIZED, VERIFY_DATA_FLOW_DISABLED, VERIFY_RESTORE_BLOCKED.
3. Then `system_id` ascending, then `resource_id` ascending (plain string sort; check the samples, e.g. does `account_10` sort before `account_9`?) **[?]**.
4. `step_no` = 1..N consecutively.

Sample `case_03` (COMPLETE) matches: ABSENT (account) then PRESENT (security) then ANONYMIZED (analytics).

## 6. Traps to design for

1. **Reported complete, but data in a replica.** The primary is clean while a failover or read replica still holds the row (`replication drift`).
2. **Sync resurrection.** The account was deleted, then a `SYNC_RECORD` or `RESTORE_BACKUP` re-created data downstream.
3. **Old identifiers.** A leftover row has the previous email, phone or hash; only the audit log links it to the user.
4. **Case-variant emails** in evidence.
5. **Time travel.** A later snapshot shows a different state than at `audit_at`; use only evidence captured at or before `audit_at`.
6. **Retention is not deletion.** Never plan to delete security audit, legal-hold or backup records. Backups are handled by blocking restore.
7. **Tombstone.** `user_id` may stay; name, email, phone and email_hash must not. A tombstone with any of those is exposed PII.
8. **Shared support threads.** Redact, don't delete, when shared customer/agent/order context must be kept; delete attachments only if they belong only to the subject.
9. **Non-deletion requests** in several languages: changing phone, correcting a surname, marketing opt-out, data copy request, "don't close my account". These get `[]`.
10. **Multi-language intent.** Don't match on English keywords only.
11. **Look-alike users.** The data includes similar people ("Mateo Ríos" vs "Mateo Rios Gil"). Match on exact identifiers, not names.

## 7. What is decided by code vs. by a model

| Job | Who | Why |
|---|---|---|
| Intent (delete vs not), 6 languages | LLM (with activity-log cross-check) | Language understanding |
| Identity resolution, joins, state, rules, ordering, CSV | Code | Must be exact and repeatable |
| `.png` / scanned PDF text | OCR first, VLM fallback | Only needed for media |

If the final run uses a model for only a small part, `usage_report.md` should say so honestly.

## 8. Invariants (use these as validators)

- Output has 518 rows, sorted by `case_id`; header is `case_id,deletion_status,steps_json`.
- NOT_APPLICABLE implies `steps_json == []`.
- COMPLETE implies every step has `phase == VERIFICATION` and a non-empty `evidence_id`.
- INCOMPLETE implies at least one FINDING; every FINDING has a non-empty `evidence_id`; every REMEDIATION and VERIFICATION has `evidence_id == ""`.
- Every FINDING has a matching REMEDIATION and a matching VERIFICATION on the same `(system_id, resource_id)`.
- `(phase, operation, state)` is always one of the allowed combinations.
- No DELETE_RECORD on retained categories (audit_record, legal_hold, backup).
- No state taken from evidence captured after `audit_at`.
- Evidence ids exist in `evidence_files.csv`, `system_activity.csv` or `user_audit_log.csv`.
- Same input twice gives byte-identical output.

## 9. Open questions to resolve with data (do these first)

1. How is `email_hash` computed (which hash, which normalization)?
2. How do `system_id` values map to prefixes in the sample answers (e.g. `identity_service` for tombstones)?
3. Tie-break and string ordering for ids of different lengths.
4. What exactly does a tombstone's expected treatment look like in a COMPLETE vs INCOMPLETE answer?
5. How do telemetry and secondary identifiers show up in the evidence?
6. How is a retention period or legal hold read (PDF register, security_audit_records table)?
7. What do the PNG screenshots show, and which cases depend on them?
8. Which `evidence_id` is the right one to cite when several files show the same fact (the samples show the pattern; see `case_05` citing the failover replica capture)?

Answer these with small scripts against the sample cases **before** writing the full pipeline.
