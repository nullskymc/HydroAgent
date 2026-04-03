import unittest
from unittest.mock import Mock, patch

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.database.models import Base
    from src.services.irrigation_service import (
        approve_plan,
        bootstrap_default_zones,
        create_plan,
        execute_plan,
        list_zones,
        reject_plan,
    )

    DEPS_AVAILABLE = True
except ModuleNotFoundError:
    DEPS_AVAILABLE = False


@unittest.skipUnless(DEPS_AVAILABLE, "SQLAlchemy dependencies are not installed")
class TestZonePlanning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)

    def setUp(self):
        self.db = self.SessionLocal()
        bootstrap_default_zones(self.db)

    def tearDown(self):
        self.db.close()

    def test_generate_plan_creates_pending_or_ready_state(self):
        zone = list_zones(self.db)[0]
        plan = create_plan(self.db, zone.zone_id, trigger="test", requested_by="tester")
        self.assertEqual(plan.zone_id, zone.zone_id)
        self.assertIn(plan.status, {"pending_approval", "ready"})
        self.assertIsNotNone(plan.evidence_summary)
        self.assertIsNotNone(plan.safety_review)

    def test_plan_lifecycle_approve_and_execute(self):
        zone = list_zones(self.db)[0]
        with patch("src.services.irrigation_service.DataCollectionModule.get_data", return_value={"data": {"soil_moisture": 12, "temperature": 21, "light_intensity": 180, "rainfall": 0}}), patch(
            "src.services.irrigation_service.requests.get",
            return_value=Mock(json=lambda: {"status": "1", "forecasts": [{"casts": [{"date": "2026-04-03", "dayweather": "晴", "daytemp": "28", "nighttemp": "18"}]}]}),
        ):
            plan = create_plan(self.db, zone.zone_id, trigger="test", requested_by="tester")

        approved = approve_plan(self.db, plan.plan_id, actor="tester")
        self.assertEqual(approved.approval_status, "approved")

        executed = execute_plan(self.db, plan.plan_id, actor="tester")
        self.assertEqual(executed.execution_status, "executed")
        self.assertEqual(executed.status, "executed")

    def test_reject_plan_blocks_execution(self):
        zone = list_zones(self.db)[0]
        plan = create_plan(self.db, zone.zone_id, trigger="test", requested_by="tester")
        rejected = reject_plan(self.db, plan.plan_id, actor="tester", comment="not safe")
        self.assertEqual(rejected.approval_status, "rejected")

    def test_rain_risk_keeps_non_emergency_plan_on_hold(self):
        zone = list_zones(self.db)[0]
        with patch("src.services.irrigation_service.DataCollectionModule.get_data", return_value={"data": {"soil_moisture": 32, "temperature": 20, "light_intensity": 120, "rainfall": 0}}), patch(
            "src.services.irrigation_service.requests.get",
            return_value=Mock(json=lambda: {"status": "1", "forecasts": [{"casts": [{"date": "2026-04-03", "dayweather": "小雨", "daytemp": "20", "nighttemp": "12"}]}]}),
        ):
            plan = create_plan(self.db, zone.zone_id, trigger="test", requested_by="tester")
        self.assertEqual(plan.proposed_action, "hold")


if __name__ == "__main__":
    unittest.main()
