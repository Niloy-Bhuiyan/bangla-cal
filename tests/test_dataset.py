import copy
import json
from pathlib import Path
import tempfile
import unittest

from dataset.validate import load_questions


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.example = load_questions("dataset/examples.jsonl")[0]

    def check_invalid(self, rows, reviewed=False):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_questions(path, reviewed)

    def test_review_gate(self):
        self.check_invalid([self.example], reviewed=True)

    def test_invalid_categories_and_missing_ground_truth(self):
        for key, value in [("category", "invented"), ("ground_truth_answer", None),
                           ("reviewed_by", ["same", "same"]), ("question_bn", "English only")]:
            row = copy.deepcopy(self.example)
            row[key] = value
            self.check_invalid([row])

    def test_duplicate_and_unlabelled_draft(self):
        self.check_invalid([self.example, self.example])
        self.check_invalid([{**self.example, "notes": "draft"}])


if __name__ == "__main__":
    unittest.main()
