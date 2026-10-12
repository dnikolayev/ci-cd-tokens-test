import copy
import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import plot_results
import report


def trial(cap=1, repeat=1, **updates):
    record = {
        "trial": f"example-{cap}-{repeat}", "fault": "none", "monitor": "poll",
        "parallel": cap, "repeat": repeat, "success": True,
        "repo": "example/ci-demo", "run_id": cap * 100 + repeat,
        "elapsed_seconds": 20, "observer_invocations": 2,
        "dispatch_started": "2026-01-01T00:00:00Z", "verified_at": "2026-01-01T00:00:10Z",
        "usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10},
    }
    record.update(updates)
    return record


class ReportTests(unittest.TestCase):
    def test_failed_trial_stays_in_means_and_usage_per_success(self):
        failed = trial(repeat=2, success=False, elapsed_seconds=40, observer_invocations=4,
                       usage={"input_tokens": 300, "cached_input_tokens": 200, "output_tokens": 30})
        cell = report.summarize(report.prepare([trial(), failed]))[0]
        self.assertEqual((cell["n"], cell["successes"]), (2, 1))
        self.assertEqual(cell["elapsed_seconds"], 30)
        self.assertEqual(cell["input_tokens"], 200)
        self.assertEqual(cell["total_tokens"], 220)
        self.assertEqual(cell["tokens_per_success"], 440)

    def test_missing_usage_makes_cell_usage_unknown_without_dropping_trial(self):
        failed = trial(repeat=2, success=False, usage=None)
        cell = report.summarize(report.prepare([trial(), failed]))[0]
        self.assertEqual((cell["n"], cell["successes"]), (2, 1))
        for field in (*report.TOKEN_FIELDS, "tokens_per_success"):
            self.assertIsNone(cell[field])
        self.assertEqual(cell["elapsed_seconds"], 20)

    def test_unknown_cache_does_not_hide_known_input_and_output(self):
        cell = report.summarize(report.prepare([trial(usage={"input_tokens": 100, "output_tokens": 10})]))[0]
        self.assertIsNone(cell["cached_input_tokens"])
        self.assertIsNone(cell["uncached_input_tokens"])
        self.assertEqual(cell["total_tokens"], 110)

    def test_no_success_has_no_usage_per_success(self):
        cell = report.summarize(report.prepare([trial(success=False)]))[0]
        self.assertEqual(cell["tokens_per_success"], "n/a")
        self.assertEqual(cell["total_tokens"], 110)

    def test_pair_difference_has_correct_direction_and_keeps_failure(self):
        fast = trial(cap=4, success=False, elapsed_seconds=12,
                     verified_at="2026-01-01T00:00:05Z",
                     usage={"input_tokens": 50, "cached_input_tokens": 20, "output_tokens": 5})
        pair = report.paired(report.prepare([trial(), fast]))[0]
        self.assertEqual(pair["elapsed_seconds"], 8)
        self.assertEqual(pair["ci_seconds"], 5)
        self.assertEqual(pair["total_tokens"], 55)
        self.assertEqual(pair["uncached_input_tokens"], -10)
        self.assertEqual(pair["successes"], "yes / no")

    def test_missing_pair_member_is_visible(self):
        pair = report.paired(report.prepare([trial()]))[0]
        self.assertEqual(pair["successes"], "yes / missing")
        self.assertIsNone(pair["total_tokens"])
        self.assertIn("yes / missing", report.render([trial()]))

    def test_duplicate_pair_or_trial_id_is_rejected(self):
        for duplicate in (trial(trial="different-id"), trial(cap=4, trial="example-1-1")):
            with self.subTest(duplicate=duplicate), self.assertRaises(ValueError):
                report.render([trial(), duplicate])

    def test_mixed_model_or_source_is_rejected(self):
        for field in ("model", "source_sha", "hold_seconds", "use_user_config"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                report.render([trial(**{field: "first"}), trial(cap=4, **{field: "second"})])

    def test_invalid_usage_or_duration_is_rejected(self):
        bad = [trial(usage={"input_tokens": 10, "cached_input_tokens": 11, "output_tokens": 2}),
               trial(usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 99}),
               trial(elapsed_seconds=float("nan")), trial(elapsed_seconds=True),
               trial(verified_at="2025-12-31T23:59:59Z"),
               trial(verified_at="2026-01-01T00:00:10")]
        for record in bad:
            with self.subTest(record=record), self.assertRaises(ValueError):
                report.render([record])

    def test_zero_input_is_unavailable_but_zero_output_is_valid(self):
        with self.assertRaisesRegex(ValueError, "Zero input"):
            report.render([trial(usage={"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 20})])
        measured = report.prepare([trial(usage={"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 0})])[0]
        self.assertEqual(measured["total_tokens"], 100)

    def test_legacy_job_count_and_caps_are_explicit_after_preparation(self):
        row = report.prepare([trial()])[0]
        self.assertEqual(row["job_count"], 4)
        self.assertEqual(row["planned_caps"], [1, 4])
        pair = report.paired([row])[0]
        self.assertEqual((pair["baseline_cap"], pair["comparison_cap"]), (1, 4))

    def test_scaling_compares_every_cap_to_the_intended_baseline(self):
        caps = [4, 8, 16, 32]
        records = [trial(cap=cap, job_count=32, planned_caps=caps, elapsed_seconds=320 / cap) for cap in caps]
        pairs = report.paired(report.prepare(records))
        self.assertEqual([(pair["baseline_cap"], pair["comparison_cap"]) for pair in pairs], [(4, 8), (4, 16), (4, 32)])
        self.assertEqual([pair["elapsed_seconds"] for pair in pairs], [40, 60, 70])
        text = report.render(records)
        self.assertIn("Each workflow schedules 32 jobs", text)
        self.assertIn("Baseline cap | Comparison cap", text)

    def test_scaling_keeps_missing_baseline_and_comparison_caps_visible(self):
        caps = [4, 8, 16, 32]
        rows = report.prepare([trial(cap=8, job_count=32, planned_caps=caps)])
        pairs = report.paired(rows)
        self.assertEqual([pair["successes"] for pair in pairs], ["missing / yes", "missing / missing", "missing / missing"])
        self.assertTrue(all(pair["baseline_cap"] == 4 and pair["elapsed_seconds"] is None for pair in pairs))
        rows = report.prepare([trial(cap=cap, job_count=32, planned_caps=caps) for cap in (4, 8, 32)])
        missing = report.paired(rows)[1]
        self.assertEqual(missing["comparison_cap"], 16)
        self.assertEqual(missing["successes"], "yes / missing")

    def test_invalid_scaling_caps_and_job_counts_are_rejected(self):
        invalid = [trial(cap=8, job_count=4, planned_caps=[1, 8]),
                   trial(cap=4, job_count=8),
                   trial(cap=32, job_count=32, planned_caps=[4, 8, 16])]
        invalid += [trial(cap=4, job_count=32, planned_caps=caps)
                    for caps in (None, [], [4, 4], [True, 4], [2, 4], [4, 64], "4,8")]
        for record in invalid:
            with self.subTest(record=record), self.assertRaises(ValueError):
                report.prepare([record])

    def test_mixed_job_counts_or_cap_plans_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "job_count"):
            report.prepare([trial(), trial(cap=4, job_count=32)])
        with self.assertRaisesRegex(ValueError, "Mixed planned caps"):
            report.prepare([trial(cap=4, job_count=32, planned_caps=[4, 8]),
                            trial(cap=8, job_count=32, planned_caps=[4, 8, 16])])

    def test_cap_order_does_not_change_the_intended_baseline(self):
        rows = report.prepare([trial(cap=4, job_count=32, planned_caps=[32, 4, 16, 8]),
                               trial(cap=8, job_count=32, planned_caps=[4, 8, 16, 32])])
        self.assertEqual(rows[0]["planned_caps"], [4, 8, 16, 32])
        self.assertTrue(all(pair["baseline_cap"] == 4 for pair in report.paired(rows)))

    def test_plot_preserves_legacy_pairs_and_shows_missing_scaling_caps(self):
        caps = [4, 8, 16, 32]
        cases = [([trial(), trial(cap=4, success=False, elapsed_seconds=12)], [1, 4], [20, 12]),
                 ([trial(cap=cap, job_count=32, planned_caps=caps, success=cap != 8, elapsed_seconds=320 / cap)
                   for cap in (4, 8, 32)], caps, [80, 40, None, 10])]
        for records, intended, expected in cases:
            with self.subTest(caps=intended), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "trials.jsonl"
                source.write_text("".join(json.dumps(record) + "\n" for record in records))
                matplotlib, pyplot = Mock(), Mock()
                matplotlib.pyplot = pyplot
                figure, axes = Mock(), [Mock() for _ in range(3)]
                pyplot.subplots.return_value = (figure, axes)
                with patch.dict("sys.modules", {"matplotlib": matplotlib, "matplotlib.pyplot": pyplot}), \
                     patch("sys.argv", ["plot_results.py", str(source), "--output", str(Path(directory) / "plot.png")]):
                    plot_results.main()
                line = axes[0].plot.call_args_list[0]
                self.assertEqual(line.args[0], list(range(len(intended))))
                for observed, wanted in zip(line.args[1], expected):
                    self.assertTrue(math.isnan(observed)) if wanted is None else self.assertEqual(observed, wanted)
                self.assertEqual(line.kwargs["linestyle"], "--")
                failed = axes[0].plot.call_args_list[1]
                self.assertEqual(failed.args, (1, expected[1]))
                self.assertEqual(failed.kwargs["marker"], "x")
                self.assertEqual(axes[0].set.call_args.kwargs["xticklabels"], [str(cap) for cap in intended])

    def test_harness_error_record_is_retained_with_unknown_metrics(self):
        failure = {"fault": "once", "monitor": "wait", "parallel": 4, "repeat": 1,
                   "success": False, "usage": None, "measurement_error": "harness_error"}
        text = report.render([failure])
        self.assertIn("All 1 recorded trials are included; 0/1 completed verification.", text)
        self.assertIn("unknown", text)
        self.assertIn("unavailable", text)

    def test_report_links_workflow_and_does_not_mutate_records(self):
        record = trial()
        original = copy.deepcopy(record)
        text = report.render([record])
        self.assertIn("[101](https://github.com/example/ci-demo/actions/runs/101)", text)
        self.assertEqual(record, original)

    def test_malformed_input_fails_without_skipping_a_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            path.write_text('{}\ninvalid\n')
            with self.assertRaisesRegex(ValueError, "line 2"):
                report.read_records(path)

    def test_cli_writes_report_and_preserves_source_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "trials.jsonl"
            output = Path(directory) / "reports" / "pilot.md"
            original = json.dumps(trial()) + "\n"
            source.write_text(original)
            with patch("sys.argv", ["report.py", str(source), "--output", str(output)]):
                report.main()
            self.assertIn("# Synthetic CI pilot report", output.read_text())
            with patch("sys.argv", ["report.py", str(source), "--output", str(source)]), \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                report.main()
            self.assertEqual(source.read_text(), original)


if __name__ == "__main__":
    unittest.main()
