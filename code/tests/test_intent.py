"""Unit tests for code/intent.py."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest
from code.intent import classify_all_requests, classify_intent_offline
from code.loader import load_dataset


class TestIntent(unittest.TestCase):
    def test_samples_all_delete(self):
        """All 32 samples in sample_deletion_requests must be classified as DELETE."""
        ds = load_dataset()
        for req in ds.sample_requests:
            cid = req["case_id"]
            txt = req["request_text"]
            res = classify_intent_offline(cid, txt)
            self.assertEqual(
                res.intent,
                "DELETE",
                f"Sample case {cid} should be DELETE, got {res.intent} ({res.reason})",
            )

    def test_custom_cases_benchmark(self):
        """Custom multilingual benchmark cases must achieve >= 95% accuracy."""
        cases_path = (
            Path(__file__).resolve().parent.parent
            / "evaluation"
            / "custom_cases"
            / "intent_cases.json"
        )
        with open(cases_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        correct = 0
        total = len(cases)
        for i, c in enumerate(cases):
            res = classify_intent_offline(f"custom_{i}", c["text"])
            if res.intent == c["expected"]:
                correct += 1
            else:
                print(f"FAILED: {c['text']} -> expected {c['expected']}, got {res.intent}")

        acc = correct / total
        self.assertGreaterEqual(
            acc, 0.95, f"Accuracy {acc:.2%} is below 95% threshold ({correct}/{total})"
        )

    def test_dataset_non_deletion_count(self):
        """Exactly 10 specific non-deletion requests exist in the 518 dataset."""
        ds = load_dataset()
        results = classify_all_requests(ds.requests)
        non_del_cases = [cid for cid, r in results.items() if r.intent == "NOT_DELETE"]
        expected_non_del = {
            "case_533",
            "case_534",
            "case_535",
            "case_536",
            "case_537",
            "case_538",
            "case_539",
            "case_540",
            "case_541",
            "case_542",
        }
        self.assertEqual(
            set(non_del_cases),
            expected_non_del,
            f"Non-deletion cases mismatch: got {non_del_cases}",
        )


if __name__ == "__main__":
    unittest.main()
