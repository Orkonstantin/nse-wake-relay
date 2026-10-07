"""Exercise the actual embedded collector offline; no HTTP requests or runner sleeps."""
import os
import textwrap
from unittest.mock import patch
import unittest
from datetime import datetime, timezone
from pathlib import Path


def collector():
    workflow = (Path(__file__).parents[1] / ".github/workflows/activity-evidence.yml").read_text()
    # The final run block is Python; extract it without YAML dependencies.
    source = workflow.split("        run: |\n", 1)[1]
    namespace = {"__name__": "offline_collector_test"}
    with patch.dict(os.environ, {"HEALTH_URL": "https://invalid.example/health"}):
        exec(compile(textwrap.dedent(source), "activity-evidence.yml", "exec"), namespace)
    return namespace


class WorkerStartClassification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = collector()

    def check(self, started="2026-10-07T08:00:02Z", phase="running", late=0, restarts=0):
        target = datetime(2026, 10, 7, 8, 30, tzinfo=timezone.utc)
        h = {"duty_cycle": {"enabled": True, "in_window": True, "phase": phase,
             "windows_run": 1, "last_started_at": started, "closes_at": "2026-10-08T00:00:00Z"},
             "supervisor": {"restarts": restarts, "starts": 1, "failures_in_window": 0,
                            "gave_up": False, "last_started_at": "2026-10-07T07:46:23Z"}}
        from datetime import timedelta
        probe = {"sent": target + timedelta(seconds=late), "body": h, "http": 200,
                 "cls": "already_up", "seconds": 0.2, "error": None}
        result = self.module["judge"]("C2", target, probe, {})
        return {c["name"]: c for c in result["checks"]}, result

    def test_timely_direct_timestamp_passes(self):
        checks, _ = self.check()
        self.assertEqual(checks["worker_started"]["result"], "PASS")

    def test_midday_deploy_counters_one_cannot_prove_first_start(self):
        checks, result = self.check(started="2026-10-07T13:55:15Z", late=22000)
        self.assertEqual(checks["worker_started"]["result"], "MISSING")
        self.assertIn("not retained across deployments", checks["worker_started"]["detail"])
        self.assertEqual(checks["server_live"]["result"], "MISSING")
        self.assertNotEqual(result["verdict"], "PASS")

    def test_even_on_time_probe_cannot_prove_late_start_was_first(self):
        checks, _ = self.check(started="2026-10-07T08:10:00Z")
        self.assertEqual(checks["worker_started"]["result"], "MISSING")

    def test_actual_inactive_worker_still_fails(self):
        checks, _ = self.check(phase="idle")
        self.assertEqual(checks["worker_started"]["result"], "FAIL")

    def test_pre_window_timestamp_still_fails(self):
        checks, _ = self.check(started="2026-10-07T07:59:00Z")
        self.assertEqual(checks["worker_started"]["result"], "FAIL")

    def test_restarted_first_start_still_missing(self):
        checks, _ = self.check(restarts=1)
        self.assertEqual(checks["worker_started"]["result"], "MISSING")
