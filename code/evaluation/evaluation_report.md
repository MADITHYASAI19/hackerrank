# Evaluation Report

## 1. Case-Level Deletion Status Accuracy

- **Status Accuracy**: 25/32 (78.12%)
- **Exact Sequence Match**: 1/32 (3.12%)
- **Average Edit Distance**: 19.12 steps per case

### Confusion Matrix

| Gold \ Pred | COMPLETE | INCOMPLETE | NOT_APPLICABLE |
| --- | --- | --- | --- |
| **COMPLETE** | 4 | 6 | 0 |
| **INCOMPLETE** | 1 | 21 | 0 |
| **NOT_APPLICABLE** | 0 | 0 | 0 |

## 2. Step-Level Accuracy

- **Gold Steps Total**: 193
- **Predicted Steps Total**: 682
- **True Positive Steps**: 114
- **Step Precision**: 0.1672 (16.72%)
- **Step Recall**: 0.5907 (59.07%)
- **Step F1**: 0.2606 (26.06%)

## 3. Field-Level Accuracy

| Field | Correct / Total | Accuracy |
| --- | --- | --- |
| `step_no` | 178 / 697 | 25.54% |
| `phase` | 72 / 697 | 10.33% |
| `system_id` | 48 / 697 | 6.89% |
| `resource_id` | 31 / 697 | 4.45% |
| `operation` | 40 / 697 | 5.74% |
| `state` | 76 / 697 | 10.90% |
| `evidence_id` | 66 / 697 | 9.47% |
