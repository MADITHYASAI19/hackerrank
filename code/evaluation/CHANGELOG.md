# Evaluation Changelog

## [Baseline] Initial Evaluation on sample_deletion_requests.csv (32 cases)

- **Status Accuracy**: 25/32 (78.12%)
  - COMPLETE: 4 predicted, 10 gold (6 false INCOMPLETE)
  - INCOMPLETE: 21 predicted, 22 gold (1 false COMPLETE)
  - NOT_APPLICABLE: 0 (all 32 samples are actual deletion requests)
- **Exact Sequence Match**: 1/32 (3.12%)
- **Average Edit Distance**: 19.12 steps per case
- **Step Metrics**:
  - Gold Steps Total: 193
  - Predicted Steps Total: 682
  - True Positive Steps: 114
  - Precision: 0.1672 (16.72%)
  - Recall: 0.5907 (59.07%)
  - F1 Score: 0.2606 (26.06%)
- **Field Accuracy**:
  - step_no: 178/697 (25.54%)
  - phase: 72/697 (10.33%)
  - system_id: 48/697 (6.89%)
  - resource_id: 31/697 (4.45%)
  - operation: 40/697 (5.74%)
  - state: 76/697 (10.90%)
  - evidence_id: 66/697 (9.47%)

### Root Causes Identified for Investigation:
1. **Candidate user_id Over-matching**: `IdentitySet.matches()` checked if `self.user_id in v_str`. For `user_21`, it matched `user_210`, `user_211`, `user_213`, etc., bringing dozens of unrelated users' resources into each case.
2. **Missing stringified JSON unpacking**: Tables storing `record_json` string columns weren't unpacked into structured dictionaries, causing field lookups to miss or incorrectly match.
3. **Log kv parsing**: Key-value extraction in `.log` files only captured `resource_id` instead of parsing all structured attributes (such as `subject_ref`, `correlation_key`, `matched_value`).
4. **Primary Account Linking**: The candidate resource selection relied solely on activities mentioning the email or direct text, but deletion worker primary profile submissions occur between `requested_at` and `reported_at`.
