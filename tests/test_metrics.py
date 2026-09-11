import unittest

from metrics.core import (abstention_precision, abstention_recall, bootstrap, brier,
                          calibration_bins, ece, hallucination_rate, risk_coverage, summarize)


def row(qid, confidence=0.8, grade="correct", **overrides):
    return {"question_id": str(qid), "provider": "synthetic", "model": "test",
            "category": "factual_high_certainty", "expected_behavior": "answer",
            "ground_truth_answer": "x", "confidence": confidence,
            "self_consistency": confidence, "grade": grade, "abstained": False,
            "specific_unfounded": False, "confident_language": False, "behavior_met": True,
            **overrides}


class MetricsTests(unittest.TestCase):
    def test_known_ece_and_brier(self):
        # Bin [0,.5): conf=.25, acc=.5. Bin [.5,1]: conf=.75, acc=1.
        # ECE=.5*.25 + .5*.25=.25. Brier=(.04+.49+.09+.04)/4=.165.
        p, y = [0.2, 0.3, 0.7, 0.8], [0, 1, 1, 1]
        self.assertAlmostEqual(ece(p, y, bins=2), 0.25)
        self.assertAlmostEqual(brier(p, y), 0.165)
        self.assertEqual(ece([0, 1], [0, 1]), 0)
        self.assertEqual(brier([0, 1], [1, 0]), 1)
        self.assertEqual(sum(b["n"] for b in calibration_bins([0, 0.5, 1], [0, 1, 1], 2)), 3)

    def test_empty_invalid_and_boundaries(self):
        self.assertIsNone(ece([], []))
        self.assertIsNone(brier([], []))
        for p, y in [([float("nan")], [1]), ([1.2], [1]), ([0.5], []), ([0.5], [0.5])]:
            with self.assertRaises(ValueError):
                ece(p, y)

    def test_hallucination_and_abstention_denominators(self):
        rows = [row(1, category="unanswerable_adversarial", expected_behavior="abstain", abstained=True),
                row(2, category="unanswerable_adversarial", expected_behavior="abstain", specific_unfounded=True),
                row(3, abstained=True), row(4)]
        self.assertEqual(hallucination_rate(rows), 0.5)
        self.assertEqual(abstention_recall(rows), 0.5)
        self.assertEqual(abstention_precision(rows), 0.5)
        self.assertIsNone(abstention_precision([row(1)]))
        self.assertIsNone(hallucination_rate([row(1)]))

    def test_risk_curve_ties_and_abstention(self):
        rows = [row(1, 0.9), row(2, 0.9, "incorrect"), row(3, 0.5), row(4, 1, abstained=True)]
        curve = risk_coverage(rows)
        point = next(p for p in curve if p["threshold"] == 0.9)
        self.assertEqual(point["coverage"], 0.5)
        self.assertEqual(point["risk"], 0.5)
        self.assertIsNone(curve[0]["risk"])
        self.assertEqual(curve[-1]["coverage"], 0.75)

    def test_bootstrap_exact_constant_and_reproducibility(self):
        rows = [row(i, 1) for i in range(5)]
        statistic = lambda sample: brier([r["confidence"] for r in sample], [1] * len(sample))
        result = bootstrap(rows, statistic, resamples=100, seed=7)
        self.assertEqual(result["ci95"], [0, 0])
        self.assertEqual(result, bootstrap(rows, statistic, 100, 7))
        missing = bootstrap(rows, hallucination_rate, 100)
        self.assertIsNone(missing["ci95"])
        self.assertEqual(missing["valid_resamples"], 0)

    def test_bootstrap_resamples_questions_as_clusters(self):
        rows = [row("a"), row("a"), row("b"), row("b")]
        def paired(sample):
            self.assertTrue(all(sum(r["question_id"] == q for r in sample) % 2 == 0 for q in ["a", "b"]))
            return 1.0
        self.assertEqual(bootstrap(rows, paired, 50)["n_questions"], 2)

    def test_category_eligibility_and_duplicate_guard(self):
        results = summarize([row(1), row(2, category="temporally_unstable", ground_truth_answer=None)], 20)
        self.assertEqual(results["synthetic/test/overall"]["n_calibration"], 1)
        with self.assertRaises(ValueError):
            summarize([row(1), row(1)], 20)
