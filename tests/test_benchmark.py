import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark


def job(shard, *, attempt=1, conclusion="success", status="completed", start=0, end=10):
    return {
        "id": attempt * 100 + shard,
        "name": f"synthetic ({shard})",
        "attempt": attempt,
        "status": status,
        "conclusion": conclusion,
        "checks_conclusion": "success",
        "hold_conclusion": conclusion,
        "steps": [
            {"name": "Run unchanged checks", "conclusion": "success"},
            {"name": "Hold and optionally fail", "conclusion": conclusion},
        ],
        "started_at": f"2026-01-01T00:00:{start:02d}Z",
        "completed_at": f"2026-01-01T00:00:{end:02d}Z",
    }


class UsageTests(unittest.TestCase):
    def test_terminal_usage_does_not_double_count_cache_or_reasoning(self):
        events = [
            {"type": "item.completed", "usage": {"input_tokens": 999}},
            {"type": "turn.completed", "usage": {
                "input_tokens": 100, "cached_input_tokens": 70,
                "cache_write_input_tokens": 5, "output_tokens": 20,
                "reasoning_output_tokens": 8,
            }},
        ]
        result = benchmark.usage(events)
        self.assertEqual(result["uncached_input_tokens"], 30)
        self.assertEqual(result["total_tokens"], 120)
        self.assertEqual(result["reasoning_output_tokens"], 8)

    def test_exactly_one_terminal_event_is_required(self):
        terminal = {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}}
        for events in ([], [terminal, terminal]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                benchmark.usage(events)

    def test_unreported_counters_remain_unknown(self):
        result = benchmark.usage([{"type": "turn.completed", "usage": {
            "input_tokens": 100, "output_tokens": 20,
        }}])
        for field in ("cached_input_tokens", "uncached_input_tokens",
                      "cache_write_input_tokens", "reasoning_output_tokens"):
            self.assertIsNone(result[field])

    def test_rejects_invalid_counters(self):
        for field in benchmark.TOKEN_FIELDS:
            for value in (-1, True, 1.5, "1"):
                counters = {"input_tokens": 100, "output_tokens": 20, field: value}
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    benchmark.usage([{"type": "turn.completed", "usage": counters}])
        with self.assertRaises(ValueError):
            benchmark.usage([{"type": "turn.completed", "usage": {
                "input_tokens": 10, "cached_input_tokens": 11, "output_tokens": 2,
            }}])

    def test_required_counters_cannot_be_missing(self):
        for counters in ({}, {"input_tokens": 1}, {"output_tokens": 1},
                         {"input_tokens": 0, "output_tokens": 0}):
            with self.subTest(counters=counters), self.assertRaises(ValueError):
                benchmark.usage([{"type": "turn.completed", "usage": counters}])


class AcceptanceTests(unittest.TestCase):
    def test_clean_job_retains_only_public_measurement_fields(self):
        raw = dict(job(1), labels=["synthetic-runner"], runner_name="synthetic-host",
                   logs="synthetic log text", environment={"example": "synthetic-value"})
        cleaned = benchmark.clean_job(raw, 1)
        self.assertEqual(set(cleaned), {
            "attempt", "id", "name", "status", "conclusion", "created_at",
            "started_at", "completed_at", "checks_conclusion", "hold_conclusion",
        })
        self.assertEqual(cleaned["checks_conclusion"], "success")
        self.assertEqual(cleaned["hold_conclusion"], "success")

    def test_success_requires_all_four_exact_jobs(self):
        jobs = [job(n) for n in range(1, 5)]
        self.assertTrue(benchmark.accepted([jobs], "none"))
        for invalid in (jobs[:-1], jobs + [job(5)], jobs[:-1] + [job(1)]):
            with self.subTest(jobs=invalid):
                self.assertFalse(benchmark.accepted([invalid], "none"))

    def test_larger_workload_requires_every_job_and_preserves_single_retry(self):
        jobs = [job(n) for n in range(1, 33)]
        self.assertTrue(benchmark.accepted([jobs], "none", 32))
        for invalid in (jobs[:4], jobs[:-1], jobs + [job(33)], jobs[:-1] + [job(1)]):
            with self.subTest(jobs=len(invalid)):
                self.assertFalse(benchmark.accepted([invalid], "none", 32))
        first = [job(1, conclusion="failure"), *jobs[1:]]
        self.assertTrue(benchmark.accepted([first, [job(1, attempt=2)]], "once", 32))
        self.assertFalse(benchmark.accepted([first[:-1], [job(1, attempt=2)]], "once", 32))

    def test_skipped_cancelled_failed_or_unfinished_jobs_are_rejected(self):
        for conclusion in ("skipped", "cancelled", "failure", None):
            with self.subTest(conclusion=conclusion):
                jobs = [job(1, conclusion=conclusion)] + [job(n) for n in range(2, 5)]
                self.assertFalse(benchmark.accepted([jobs], "none"))
        jobs = [job(1, status="in_progress")] + [job(n) for n in range(2, 5)]
        self.assertFalse(benchmark.accepted([jobs], "none"))

    def test_expected_retry_preserves_successful_first_attempt_jobs(self):
        first = [job(1, conclusion="failure")] + [job(n) for n in range(2, 5)]
        self.assertTrue(benchmark.accepted([first, [job(1, attempt=2)]], "once"))
        self.assertFalse(benchmark.accepted([first], "once"))
        self.assertFalse(benchmark.accepted([first, [job(1, attempt=2)]], "none"))

    def test_wrong_failure_or_retry_is_rejected(self):
        first = [job(1, conclusion="failure")] + [job(n) for n in range(2, 5)]
        for retry in ([], [job(2, attempt=2)], [job(1, attempt=2, conclusion="failure")],
                      [job(1, attempt=2), job(2, attempt=2, start=20, end=30)]):
            with self.subTest(retry=retry):
                self.assertFalse(benchmark.accepted([first, retry], "once"))
        wrong_failure = [job(n, conclusion="failure" if n == 2 else "success") for n in range(1, 5)]
        self.assertFalse(benchmark.accepted([wrong_failure, [job(2, attempt=2)]], "once"))
        self.assertFalse(benchmark.accepted([[job(n) for n in range(1, 5)], [job(1, attempt=2)]], "once"))

    def test_skipped_or_extra_attempts_are_rejected(self):
        first = [job(1, conclusion="failure")] + [job(n) for n in range(2, 5)]
        self.assertFalse(benchmark.accepted([first, [job(1, attempt=3)]], "once"))
        self.assertFalse(benchmark.accepted([first, [job(1, attempt=2)], [job(1, attempt=3)]], "once"))

    def test_missing_or_failed_assertion_step_is_rejected(self):
        for conclusion in (None, "skipped", "failure"):
            first = [job(1, conclusion="failure")] + [job(n) for n in range(2, 5)]
            first[0]["checks_conclusion"] = conclusion
            with self.subTest(conclusion=conclusion):
                self.assertFalse(benchmark.accepted([first, [job(1, attempt=2)]], "once"))

    def test_carried_forward_successes_are_accepted_without_extra_execution(self):
        first = [job(1, conclusion="failure")] + [job(n) for n in range(2, 5)]
        retry = [job(1, attempt=2, start=20, end=30)] + [job(n, attempt=2) for n in range(2, 5)]
        for entry in retry:
            if benchmark.carried_forward(entry, first):
                entry["carried_forward_from_attempt"] = 1
        self.assertTrue(benchmark.accepted([first, retry], "once"))
        self.assertEqual(benchmark.job_metrics([first, retry])["job_seconds"], 50)
        self.assertEqual(benchmark.job_metrics([first, retry])["peak_overlapping_jobs"], 4)
        retry[1]["started_at"] = "2026-01-01T00:00:20Z"
        retry[1]["completed_at"] = "2026-01-01T00:00:30Z"
        self.assertFalse(benchmark.accepted([first, retry], "once"))


class TimingTests(unittest.TestCase):
    def test_touching_intervals_do_not_overlap(self):
        metrics = benchmark.job_metrics([[job(1, start=0, end=10), job(2, start=10, end=20)]])
        self.assertEqual(metrics, {"job_seconds": 20, "peak_overlapping_jobs": 1, "job_span_seconds": 20})

    def test_overlapping_work_and_retry_are_both_counted(self):
        metrics = benchmark.job_metrics([
            [job(1, start=0, end=10), job(2, start=5, end=15)],
            [job(1, attempt=2, start=20, end=30)],
        ])
        self.assertEqual(metrics, {"job_seconds": 30, "peak_overlapping_jobs": 2, "job_span_seconds": 30})

    def test_zero_length_job_does_not_add_overlap(self):
        metrics = benchmark.job_metrics([[job(1, start=0, end=0), job(2, start=0, end=10)]])
        self.assertEqual(metrics, {"job_seconds": 10, "peak_overlapping_jobs": 1, "job_span_seconds": 10})

    def test_no_timings_have_no_span(self):
        self.assertEqual(benchmark.job_metrics([]), {
            "job_seconds": 0, "peak_overlapping_jobs": 0, "job_span_seconds": None,
        })

    def test_negative_duration_is_rejected(self):
        with self.assertRaises(ValueError):
            benchmark.job_metrics([[job(1, start=10, end=0)]])

    def test_epoch_normalizes_timezone_offsets(self):
        self.assertEqual(benchmark.epoch("2026-01-01T00:00:00Z"),
                         benchmark.epoch("2026-01-01T01:00:00+01:00"))


class ObserverTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state.json"
        self.state = {
            "repo": "example/ci-demo", "ref": "main", "trial": "example-trial",
            "source_sha": "a" * 40, "run_id": 123, "parallel": 1,
            "hold_seconds": 5, "poll_seconds": 5, "timeout_seconds": 60,
            "observer_invocations": 0, "api_polls": 0, "attempts": [],
            "dispatch_started": "2026-01-01T00:00:00Z", "fault": "once", "monitor": "poll",
        }

    def observe(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            benchmark.observe(self.path)
        return json.loads(output.getvalue())

    def test_terminal_recheck_never_dispatches_or_polls(self):
        self.state.update(terminal=True, accepted=True)
        benchmark.save(self.path, self.state)
        with patch.object(benchmark, "gh") as gh, patch.object(benchmark, "api") as api:
            self.assertEqual(self.observe(), {"terminal": True, "accepted": True})
        gh.assert_not_called()
        api.assert_not_called()

    def test_dispatch_and_acceptance_use_fixed_larger_workload(self):
        self.state.pop("dispatch_started")
        self.state.pop("run_id")
        self.state.update(job_count=32, parallel=16, fault="none")
        run = {"head_sha": self.state["source_sha"], "run_attempt": 1, "status": "completed",
               "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:20Z"}
        responses = [{"workflow_runs": [{"id": 123, "display_title": "trial-example-trial"}]},
                     run, {"jobs": [job(n) for n in range(1, 33)]}]
        benchmark.save(self.path, self.state)
        with patch.object(benchmark, "api", side_effect=responses), patch.object(benchmark, "gh") as gh, \
             patch.object(benchmark.time, "sleep"), patch.object(benchmark.time, "time", return_value=0):
            self.assertTrue(self.observe()["accepted"])
        self.assertEqual(gh.call_count, 1)
        self.assertIn("jobs=32", gh.call_args.args)
        self.assertIn("parallel=16", gh.call_args.args)

    def test_retry_request_is_not_repeated_before_attempt_becomes_visible(self):
        first = [job(1, conclusion="failure")] + [job(n) for n in range(2, 5)]
        run = {"head_sha": self.state["source_sha"], "run_attempt": 1, "status": "completed",
               "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:20Z"}
        responses = [run, {"jobs": first}, run, {"jobs": first},
                     dict(run, run_attempt=2), {"jobs": [job(1, attempt=2)]}]
        benchmark.save(self.path, self.state)
        with patch.object(benchmark, "api", side_effect=responses), patch.object(benchmark, "gh") as gh, \
             patch.object(benchmark.time, "sleep"), patch.object(benchmark.time, "time", return_value=0):
            self.assertFalse(self.observe()["terminal"])
            self.assertFalse(self.observe()["terminal"])
            self.assertTrue(self.observe()["accepted"])
        gh.assert_called_once_with("run", "rerun", "123", "--failed", "--repo", "example/ci-demo")
        self.assertEqual(len(json.loads(self.path.read_text())["attempts"]), 2)

    def test_changed_workflow_source_is_rejected(self):
        benchmark.save(self.path, self.state)
        with patch.object(benchmark, "api", return_value={"head_sha": "b" * 40}), \
             patch.object(benchmark, "gh") as gh, patch.object(benchmark.time, "sleep"), \
             patch.object(benchmark.time, "time", return_value=0), self.assertRaises(ValueError):
            self.observe()
        gh.assert_not_called()

    def test_real_test_failure_is_not_treated_as_injected_failure(self):
        first = [job(1, conclusion="failure")] + [job(n) for n in range(2, 5)]
        first[0]["steps"][0]["conclusion"] = "failure"
        first[0]["steps"][1]["conclusion"] = "skipped"
        run = {"head_sha": self.state["source_sha"], "run_attempt": 1, "status": "completed",
               "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:20Z"}
        benchmark.save(self.path, self.state)
        with patch.object(benchmark, "api", side_effect=[run, {"jobs": first}]), \
             patch.object(benchmark, "gh") as gh, patch.object(benchmark.time, "sleep"), \
             patch.object(benchmark.time, "time", return_value=0):
            result = self.observe()
        self.assertTrue(result["terminal"])
        self.assertFalse(result["accepted"])
        gh.assert_not_called()


class PlanTests(unittest.TestCase):
    def args(self, directory, **updates):
        values = dict(repo="example/ci-demo", hold=15, poll=10, timeout=600, jobs=32,
                      caps=[4, 8, 16, 32], repeats=1, fault_repeats=0, seed=42,
                      output=Path(directory) / "scaling.jsonl")
        values.update(updates)
        return SimpleNamespace(**values)

    def test_scaling_plan_keeps_workload_fixed_across_every_condition(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            with patch.object(benchmark, "run_trial", return_value={
                    "success": True, "elapsed_seconds": 1, "usage": None}) as trial, \
                    contextlib.redirect_stdout(io.StringIO()):
                benchmark.pilot(args)
            specs = json.loads(args.output.with_suffix(".plan.json").read_text())["trials"]
            self.assertEqual(trial.call_count, 8)
            self.assertEqual({(s["monitor"], s["parallel"]) for s in specs},
                             {(monitor, cap) for monitor in ("poll", "wait") for cap in (4, 8, 16, 32)})
            self.assertTrue(all(s["job_count"] == 32 and s["planned_caps"] == [4, 8, 16, 32]
                                and s["fault"] == "none" for s in specs))

    def test_invalid_caps_are_rejected_before_any_trial(self):
        for changes in (dict(caps=[4, 4]), dict(caps=[]), dict(caps=[2]),
                        dict(jobs=4, caps=[4, 8]), dict(jobs=8)):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory, \
                    patch.object(benchmark, "run_trial") as trial, self.assertRaises(ValueError):
                benchmark.pilot(self.args(directory, **changes))
            trial.assert_not_called()


if __name__ == "__main__":
    unittest.main()
