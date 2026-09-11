"""Only synthetic reviewer identities in temporary fixtures; no real sign-offs."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from dataset.review import assess_reviews, prepare, question_hash
from dataset.validate import load_questions
from runner.io import read_jsonl


class DatasetReviewTests(unittest.TestCase):
    def test_blank_forms_do_not_confer_review_and_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "forms"
            prepare("dataset/examples.jsonl", output)
            paths = sorted(output.glob("*.jsonl"))
            questions = load_questions("dataset/examples.jsonl")
            result = assess_reviews(questions, paths)
            self.assertEqual(result["n_reviewed_with_evidence"], 0)
            self.assertTrue(all(not q["reviewed_by"] for q in questions))
            with self.assertRaisesRegex(ValueError, "never overwrite"):
                prepare("dataset/examples.jsonl", output)

    def test_requires_two_distinct_version_bound_acceptances(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "forms"
            prepare("dataset/examples.jsonl", output)
            questions = load_questions("dataset/examples.jsonl")
            paths = sorted(output.glob("*.jsonl"))
            for i, path in enumerate(paths):
                rows = read_jsonl(path)
                for row in rows:
                    row.update(reviewer_id=f"synthetic-test-{i}", native_bengali_speaker=True,
                               reviewed_at="2026-01-01", decision="accept", rationale="Synthetic fixture only.")
                    row["checks"] = dict.fromkeys(row["checks"], True)
                path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            self.assertEqual(assess_reviews(questions, paths)["n_two_acceptances"], len(questions))
            self.assertEqual(assess_reviews(questions, paths)["n_reviewed_with_evidence"], 0)
            for question in questions:
                question["reviewed_by"] = ["synthetic-test-0", "synthetic-test-1"]
            self.assertEqual(assess_reviews(questions, paths)["n_reviewed_with_evidence"], len(questions))
            with self.assertRaisesRegex(ValueError, "duplicate reviewer"):
                assess_reviews(questions, [paths[0], paths[0]])
            changed = copy.deepcopy(questions)
            changed[0]["ground_truth_answer"] = "A changed answer"
            self.assertNotEqual(question_hash(changed[0]), question_hash(questions[0]))
            with self.assertRaisesRegex(ValueError, "content changed"):
                assess_reviews(changed, paths)
