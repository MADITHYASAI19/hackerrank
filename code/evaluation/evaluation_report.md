# Evaluation Report

## 1. Case-Level Deletion Status Accuracy

- **Status Accuracy**: 23/32 (71.88%)
- **Exact Sequence Match**: 1/32 (3.12%)
- **Average Edit Distance**: 21.56 steps per case

### Confusion Matrix

| Gold \ Pred | COMPLETE | INCOMPLETE | NOT_APPLICABLE |
| --- | --- | --- | --- |
| **COMPLETE** | 1 | 9 | 0 |
| **INCOMPLETE** | 0 | 22 | 0 |
| **NOT_APPLICABLE** | 0 | 0 | 0 |

## 2. Step-Level Accuracy

- **Gold Steps Total**: 193
- **Predicted Steps Total**: 801
- **True Positive Steps**: 155
- **Step Precision**: 0.1935 (19.35%)
- **Step Recall**: 0.8031 (80.31%)
- **Step F1**: 0.3119 (31.19%)

## 3. Field-Level Accuracy

| Field | Correct / Total | Accuracy |
| --- | --- | --- |
| `step_no` | 192 / 802 | 23.94% |
| `phase` | 53 / 802 | 6.61% |
| `system_id` | 39 / 802 | 4.86% |
| `resource_id` | 10 / 802 | 1.25% |
| `operation` | 25 / 802 | 3.12% |
| `state` | 59 / 802 | 7.36% |
| `evidence_id` | 95 / 802 | 11.85% |
