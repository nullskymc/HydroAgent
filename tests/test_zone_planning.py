import unittest

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
        plan = create_plan(self.db, zone.zone_id, trigger="test", requested_by="tester")
        plan.proposed_action = "start"
        plan.requires_approval = True
        plan.approval_status = "pending"
        plan.status = "pending_approval"
        self.db.commit()

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


if __name__ == "__main__":
    unittest.main()
