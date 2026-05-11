# test_db_connector.py
# =====================
# FederHub Phase 3 – Unit tests for the database connector.
# Uses an in-memory SQLite database so no external DB is needed.

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import Base, JobConfiguration, RoundMetric
from db_connector import (
    create_db_session,
    fetch_job_config,
    update_job_status,
    record_round_metric,
    get_round_metrics,
)


class TestDBConnector(unittest.TestCase):
    """Test all db_connector functions using an in-memory SQLite DB."""

    @classmethod
    def setUpClass(cls):
        """Create tables and seed a job for all tests."""
        cls.session, cls.engine = create_db_session("sqlite:///:memory:")

        # Seed a test job (mimicking Alpha's job creation)
        job = JobConfiguration(
            id=1,
            job_name="Test-FL-Job",
            round_count=5,
            local_epochs=3,
            status="draft",
        )
        cls.session.add(job)
        cls.session.commit()

    @classmethod
    def tearDownClass(cls):
        cls.session.close()

    # ── fetch_job_config ─────────────────────────────────────────────────

    def test_fetch_job_config_returns_correct_data(self):
        config = fetch_job_config(self.session, job_id=1)
        self.assertEqual(config["job_name"], "Test-FL-Job")
        self.assertEqual(config["round_count"], 5)
        self.assertEqual(config["local_epochs"], 3)
        self.assertEqual(config["status"], "draft")

    def test_fetch_job_config_missing_job_raises(self):
        with self.assertRaises(ValueError):
            fetch_job_config(self.session, job_id=999)

    # ── update_job_status ────────────────────────────────────────────────

    def test_update_job_status_valid_transition(self):
        result = update_job_status(self.session, job_id=1, new_status="running")
        self.assertEqual(result["status"], "running")

        # Verify it persists
        config = fetch_job_config(self.session, job_id=1)
        self.assertEqual(config["status"], "running")

    def test_update_job_status_invalid_raises(self):
        with self.assertRaises(ValueError):
            update_job_status(self.session, job_id=1, new_status="invalid_status")

    def test_update_job_status_missing_job_raises(self):
        with self.assertRaises(ValueError):
            update_job_status(self.session, job_id=999, new_status="running")

    # ── record_round_metric ──────────────────────────────────────────────

    def test_record_round_metric_basic(self):
        metric = record_round_metric(
            session=self.session,
            job_id=1,
            round_number=1,
            accuracy=0.85,
            loss=0.32,
            num_clients=3,
            total_samples=1000,
        )
        self.assertEqual(metric.job_id, 1)
        self.assertEqual(metric.round_number, 1)
        self.assertAlmostEqual(metric.accuracy, 0.85)
        self.assertAlmostEqual(metric.loss, 0.32)

    def test_record_round_metric_with_snapshot(self):
        snapshot = {"layer1": {"mean": 0.5, "shape": [8, 4]}}
        metric = record_round_metric(
            session=self.session,
            job_id=1,
            round_number=2,
            global_weights_snapshot=snapshot,
        )
        self.assertIsNotNone(metric.global_weights_snapshot)

    def test_final_round_waits_for_expected_clients_before_completion(self):
        job = JobConfiguration(
            id=3,
            job_name="Two-Client-Final-Round",
            round_count=1,
            local_epochs=1,
            expected_clients=2,
            status="running",
        )
        self.session.add(job)
        self.session.commit()

        record_round_metric(
            self.session,
            job_id=3,
            round_number=1,
            num_clients=1,
            total_samples=50,
        )
        config = fetch_job_config(self.session, 3)
        self.assertEqual(config["status"], "running")

        record_round_metric(
            self.session,
            job_id=3,
            round_number=1,
            num_clients=2,
            total_samples=100,
        )
        config = fetch_job_config(self.session, 3)
        self.assertEqual(config["status"], "completed")

    # ── get_round_metrics ────────────────────────────────────────────────

    def test_get_round_metrics_returns_ordered(self):
        # Insert metrics in reverse order to verify ordering
        record_round_metric(self.session, job_id=1, round_number=3, accuracy=0.9)
        record_round_metric(self.session, job_id=1, round_number=1, accuracy=0.7)
        record_round_metric(self.session, job_id=1, round_number=2, accuracy=0.8)

        metrics = get_round_metrics(self.session, job_id=1)
        self.assertGreaterEqual(len(metrics), 3)
        rounds = [m["round_number"] for m in metrics]
        self.assertEqual(rounds, sorted(rounds))

    def test_get_round_metrics_empty_job(self):
        # Job 1 has metrics, but a non-existent job should return empty
        metrics = get_round_metrics(self.session, job_id=999)
        self.assertEqual(metrics, [])

    # ── Full lifecycle ───────────────────────────────────────────────────

    def test_full_job_lifecycle(self):
        """Simulate draft → running → record metrics → completed."""
        # Create a second job
        job2 = JobConfiguration(id=2, job_name="Lifecycle-Job", round_count=2, status="draft")
        self.session.add(job2)
        self.session.commit()

        # Start
        update_job_status(self.session, 2, "running")
        config = fetch_job_config(self.session, 2)
        self.assertEqual(config["status"], "running")

        # Record rounds
        for r in range(1, config["round_count"] + 1):
            record_round_metric(self.session, job_id=2, round_number=r,
                                accuracy=0.8 + r * 0.05, loss=0.5 - r * 0.1)

        # Complete
        update_job_status(self.session, 2, "completed")
        config = fetch_job_config(self.session, 2)
        self.assertEqual(config["status"], "completed")

        # Verify metrics
        metrics = get_round_metrics(self.session, 2)
        self.assertEqual(len(metrics), 2)
        self.assertAlmostEqual(metrics[0]["accuracy"], 0.85)
        self.assertAlmostEqual(metrics[1]["accuracy"], 0.90)


if __name__ == "__main__":
    unittest.main(verbosity=2)
