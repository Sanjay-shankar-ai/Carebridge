"""
Unit Tests for Phase 10: CareBridge Data-Driven Analytics & Operational Drop-off Prioritization
Validates all 9 core metrics, multi-criteria filtering, operational risk scoring, and non-clinical guardrails.
"""

import unittest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.database.seed import seed_database
from app.services.analytics_service import CareBridgeAnalyticsService
from app.models.care_case import CareCase
from app.models.owner import CaseOwner


class TestCareBridgeAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an in-memory SQLite database for isolated test execution
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        cls.SessionFactory = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    def setUp(self):
        self.session = self.SessionFactory()
        # Seed extended demo cohort (6 cases)
        seed_database(self.session, extended=True)

    def tearDown(self):
        self.session.close()

    def test_01_all_nine_metrics_calculated(self):
        """Verifies that all 9 required closed-loop metrics are present in the response."""
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session)
        self.assertIn("metrics", res)
        self.assertIn("summary", res)
        metrics = res["metrics"]

        # Validate presence of all 9 specific metrics required by user
        required_metrics = [
            "time_from_result_to_notification",
            "patient_acknowledgement_rate",
            "referral_acceptance_rate",
            "appointment_attendance_rate",
            "drop_off_recovery_rate",
            "median_time_to_care",
            "verified_closure_rate",
            "overdue_cases",
            "unassigned_cases"
        ]
        for m in required_metrics:
            self.assertIn(m, metrics, f"Missing required metric: {m}")

        self.assertEqual(res["summary"]["total_cases"], 6)

    def test_02_time_from_result_to_notification(self):
        """Verifies calculation of elapsed time from screening result to notification."""
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session)
        notif_metric = res["metrics"]["time_from_result_to_notification"]

        self.assertGreater(notif_metric["cases_measured"], 0)
        self.assertGreater(notif_metric["average_hours"], 0.0)
        self.assertGreater(notif_metric["median_hours"], 0.0)
        self.assertIn("hrs", notif_metric["formatted"])

    def test_03_patient_acknowledgement_rate(self):
        """Verifies patient comprehension and acknowledgement rate calculation."""
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session)
        ack_metric = res["metrics"]["patient_acknowledgement_rate"]

        self.assertGreater(ack_metric["notified_count"], 0)
        self.assertGreater(ack_metric["acknowledged_count"], 0)
        self.assertGreaterEqual(ack_metric["rate_percent"], 50.0)
        self.assertLessEqual(ack_metric["rate_percent"], 100.0)

    def test_04_referral_acceptance_rate(self):
        """Verifies specialist referral acceptance tracking."""
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session)
        ref_metric = res["metrics"]["referral_acceptance_rate"]

        self.assertGreater(ref_metric["total_referrals"], 0)
        self.assertGreater(ref_metric["accepted_count"], 0)
        self.assertEqual(ref_metric["rate_percent"], 100.0)

    def test_05_appointment_attendance_rate(self):
        """Verifies diagnostic visit attendance and no-show tracking."""
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session)
        appt_metric = res["metrics"]["appointment_attendance_rate"]

        self.assertGreater(appt_metric["total_evaluated"], 0)
        self.assertGreaterEqual(appt_metric["attended_count"], 1)
        self.assertGreaterEqual(appt_metric["no_show_count"], 1)

    def test_06_drop_off_recovery_rate(self):
        """Verifies measurement of recovered cases following a journey disruption."""
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session)
        rec_metric = res["metrics"]["drop_off_recovery_rate"]

        self.assertGreater(rec_metric["stalled_count"], 0)
        self.assertGreater(rec_metric["recovered_count"], 0)
        self.assertGreaterEqual(rec_metric["rate_percent"], 0.0)

    def test_07_median_time_to_care(self):
        """Verifies calculation of median days from screening result to diagnostic workup."""
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session)
        time_metric = res["metrics"]["median_time_to_care"]

        self.assertGreater(time_metric["cases_evaluated"], 0)
        self.assertGreater(time_metric["median_days"], 0.0)

    def test_08_verified_closure_rate(self):
        """Verifies that closure rate is measured strictly against clinician-verified evidence."""
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session)
        closure_metric = res["metrics"]["verified_closure_rate"]

        self.assertGreaterEqual(closure_metric["total_closed_cases"], 1)
        self.assertGreaterEqual(closure_metric["verified_closures"], 1)
        self.assertEqual(closure_metric["rate_percent"], 100.0)

    def test_09_overdue_and_unassigned_cases(self):
        """Verifies identification of SLA breached cases and ownership gaps."""
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session)
        overdue = res["metrics"]["overdue_cases"]
        unassigned = res["metrics"]["unassigned_cases"]

        self.assertGreaterEqual(overdue["count"], 1, "Should detect at least 1 overdue case (Carlos Mendez)")
        self.assertGreaterEqual(unassigned["count"], 1, "Should detect at least 1 unassigned case (Amina)")

    def test_10_filters_by_case_status(self):
        """Validates filtering by status ('closed', 'recovering', 'overdue', 'unassigned')."""
        # Filter closed cases
        closed_res = CareBridgeAnalyticsService.calculate_all_metrics(self.session, status="closed")
        self.assertEqual(closed_res["summary"]["total_cases"], 1)

        # Filter recovering cases
        rec_res = CareBridgeAnalyticsService.calculate_all_metrics(self.session, status="recovering")
        self.assertGreaterEqual(rec_res["summary"]["total_cases"], 1)

        # Filter unassigned cases
        unassigned_res = CareBridgeAnalyticsService.calculate_all_metrics(self.session, status="unassigned")
        self.assertEqual(unassigned_res["summary"]["total_cases"], 1)

    def test_11_filters_by_provider(self):
        """Validates filtering by coordinator / specialist provider."""
        priya_owner = self.session.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        self.assertIsNotNone(priya_owner)

        priya_res = CareBridgeAnalyticsService.calculate_all_metrics(
            self.session,
            provider_id=str(priya_owner.id)
        )
        self.assertGreaterEqual(priya_res["summary"]["total_cases"], 2)

    def test_12_filters_by_date_range(self):
        """Validates date range bounding for analytics reporting."""
        now = datetime.now(timezone.utc)
        # Bounded to last 5 days
        from_dt = now - timedelta(days=5)
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session, from_date=from_dt)
        self.assertLess(res["summary"]["total_cases"], 6)

    def test_13_operational_dropoff_prioritization(self):
        """
        Validates operational drop-off risk prioritization.
        Checks:
        1. Ranking by risk score.
        2. Presence of operational reasons (plain-language explanation of why prioritized).
        3. Strict non-clinical disclaimer.
        """
        priorities = CareBridgeAnalyticsService.get_operational_dropoff_priorities(self.session)
        self.assertGreater(len(priorities), 0)

        # Check sorted order (highest score first)
        scores = [p["operational_risk_score"] for p in priorities]
        self.assertEqual(scores, sorted(scores, reverse=True))

        for p in priorities:
            self.assertIn("case_number", p)
            self.assertIn("patient_name", p)
            self.assertIn("priority_tier", p)
            self.assertIn(p["priority_tier"], ["URGENT_FOLLOWUP", "ELEVATED_ATTENTION", "ON_TRACK"])
            self.assertIn("why_prioritized", p)
            self.assertGreater(len(p["why_prioritized"]), 0)
            self.assertIn("operational_reasons", p)
            self.assertIn("disclaimer", p)
            # Ensure disclaimer makes clear it is NOT clinical risk prediction
            self.assertIn("NOT", p["disclaimer"])
            self.assertIn("clinical", p["disclaimer"].lower())

    def test_14_empty_database_graceful_handling(self):
        """Verifies that an empty database or non-matching filter returns zeroed metrics without crashing."""
        now = datetime.now(timezone.utc)
        future_dt = now + timedelta(days=365)
        res = CareBridgeAnalyticsService.calculate_all_metrics(self.session, from_date=future_dt)

        self.assertEqual(res["summary"]["total_cases"], 0)
        self.assertEqual(res["metrics"]["patient_acknowledgement_rate"]["rate_percent"], 0.0)
        self.assertEqual(res["metrics"]["appointment_attendance_rate"]["rate_percent"], 0.0)
        self.assertEqual(res["metrics"]["median_time_to_care"]["median_days"], 0.0)


if __name__ == "__main__":
    unittest.main()
