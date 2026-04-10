import unittest
from unittest.mock import patch

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.database.models import Actuator, Base, Zone
    from src.services.analytics_service import get_analytics_overview, get_plan_funnel
    from src.services.irrigation_service import (
        _sensor_summary_cache,
        _weather_summary_cache,
        approve_plan,
        bootstrap_default_zones,
        create_plan,
        execute_plan,
        generate_plan_result,
        get_plan_by_id,
        get_zone_status,
        list_zones,
        manual_override_control,
        reject_plan,
        summarize_system_irrigation,
    )
    from src.services.report_service import export_operations_report, export_zone_report

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
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.SessionLocal()
        _sensor_summary_cache.clear()
        _weather_summary_cache.clear()
        bootstrap_default_zones(self.db)

    def tearDown(self):
        self.db.close()

    def _create_start_plan(self, zone_id: str):
        with patch(
            "src.services.irrigation_service.DataCollectionModule.get_data",
            return_value={"data": {"soil_moisture": 12, "temperature": 21, "light_intensity": 180, "rainfall": 0}},
        ), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={
                "city": "北京",
                "forecast": [
                    {"date": "2026-04-03", "dayweather": "晴", "daytemp": "28", "nighttemp": "18"}
                ],
            },
        ):
            return create_plan(self.db, zone_id, trigger="test", requested_by="tester")

    def test_generate_start_plan_creates_single_pending_plan(self):
        zone = list_zones(self.db)[0]
        plan = self._create_start_plan(zone.zone_id)
        self.assertEqual(plan.zone_id, zone.zone_id)
        self.assertEqual(plan.status, "pending_approval")
        self.assertIsNotNone(plan.evidence_summary)
        self.assertIsNotNone(plan.safety_review)

    def test_plan_lifecycle_approve_and_execute(self):
        zone = list_zones(self.db)[0]
        plan = self._create_start_plan(zone.zone_id)

        approved = approve_plan(self.db, plan.plan_id, actor="tester")
        self.assertEqual(approved.status, "approved")

        executed = execute_plan(self.db, plan.plan_id, actor="tester")
        self.assertEqual(executed.execution_status, "running")
        self.assertEqual(executed.status, "executing")

    def test_reject_plan_blocks_execution(self):
        zone = list_zones(self.db)[0]
        plan = self._create_start_plan(zone.zone_id)
        rejected = reject_plan(self.db, plan.plan_id, actor="tester", comment="not safe")
        self.assertEqual(rejected.status, "rejected")

    def test_rain_risk_returns_suggestion_instead_of_formal_plan(self):
        zone = list_zones(self.db)[0]
        with patch("src.services.irrigation_service.DataCollectionModule.get_data", return_value={"data": {"soil_moisture": 32, "temperature": 20, "light_intensity": 120, "rainfall": 0}}), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={
                "city": "北京",
                "forecast": [
                    {"date": "2026-04-03", "dayweather": "小雨", "daytemp": "20", "nighttemp": "12"}
                ],
            },
        ):
            result = generate_plan_result(self.db, zone.zone_id, trigger="test", requested_by="tester")
        self.assertTrue(result["suggestion_only"])
        self.assertIsNone(result["plan"])
        self.assertEqual(result["suggestion"]["proposed_action"], "hold")

    def test_generate_plan_reuses_existing_open_plan_by_default(self):
        zone = list_zones(self.db)[0]
        first = self._create_start_plan(zone.zone_id)

        with patch("src.services.irrigation_service.DataCollectionModule.get_data", return_value={"data": {"soil_moisture": 10, "temperature": 24, "light_intensity": 200, "rainfall": 0}}):
            result = generate_plan_result(self.db, zone.zone_id, trigger="test", requested_by="tester")

        plans = [plan for plan in self.db.query(type(first)).filter(type(first).zone_id == zone.zone_id).all()]
        self.assertTrue(result["reused_existing"])
        self.assertEqual(result["plan"]["plan_id"], first.plan_id)
        self.assertEqual(len(plans), 1)

    def test_generate_plan_replace_supersedes_previous_open_plan(self):
        zone = list_zones(self.db)[0]
        first = self._create_start_plan(zone.zone_id)

        with patch("src.services.irrigation_service.DataCollectionModule.get_data", return_value={"data": {"soil_moisture": 8, "temperature": 26, "light_intensity": 240, "rainfall": 0}}):
            result = generate_plan_result(self.db, zone.zone_id, trigger="test", requested_by="tester", replace=True)

        stored_first = get_plan_by_id(self.db, first.plan_id)
        self.assertFalse(result["reused_existing"])
        self.assertNotEqual(result["plan"]["plan_id"], first.plan_id)
        self.assertEqual(stored_first.status, "superseded")

    def test_manual_stop_closes_running_actuator_outside_first_zone(self):
        first_zone = list_zones(self.db)[0]
        second_zone = Zone(
            name="测试分区 B",
            location="北京",
            crop_type="测试作物",
            soil_moisture_threshold=40,
            default_duration_minutes=20,
        )
        self.db.add(second_zone)
        self.db.flush()
        second_actuator = Actuator(
            zone_id=second_zone.zone_id,
            name="测试阀门 B",
            actuator_type="valve",
            status="running",
            is_enabled=True,
        )
        self.db.add(second_actuator)
        first_zone.actuators[0].status = "idle"
        self.db.commit()

        result = manual_override_control(self.db, "stop")

        self.assertTrue(result["success"])
        self.assertEqual(second_actuator.status, "idle")
        self.assertIn(second_actuator.actuator_id, [item["actuator_id"] for item in result["stopped"]])

    def test_manual_stop_updates_plan_terminal_state_and_hides_pending_plan(self):
        zone = list_zones(self.db)[0]
        plan = self._create_start_plan(zone.zone_id)
        approve_plan(self.db, plan.plan_id, actor="tester")
        execute_plan(self.db, plan.plan_id, actor="tester")

        result = manual_override_control(self.db, "stop", zone_id=zone.zone_id)
        stored_plan = get_plan_by_id(self.db, plan.plan_id)
        zone_status = get_zone_status(self.db, zone.zone_id)

        self.assertTrue(result["success"])
        self.assertEqual(stored_plan.status, "completed")
        self.assertEqual(stored_plan.execution_status, "stopped")
        self.assertEqual(stored_plan.execution_result["stop_reason"], "manual_stop")
        self.assertEqual(stored_plan.execution_result["stopped_by"], "manual-override")
        self.assertIsNone(zone_status["pending_plan"])

    def test_status_summary_auto_stops_when_threshold_is_reached(self):
        zone = list_zones(self.db)[0]
        plan = self._create_start_plan(zone.zone_id)
        approve_plan(self.db, plan.plan_id, actor="tester")
        execute_plan(self.db, plan.plan_id, actor="tester")
        _sensor_summary_cache.clear()

        with patch("src.services.irrigation_service.DataCollectionModule.get_data", return_value={"data": {"soil_moisture": 45, "temperature": 21, "light_intensity": 180, "rainfall": 0}}):
            summary = summarize_system_irrigation(self.db)

        stored_plan = get_plan_by_id(self.db, plan.plan_id)
        self.assertEqual(summary["status"], "stopped")
        self.assertEqual(zone.actuators[0].status, "idle")
        self.assertEqual(summary["auto_stopped"][0]["reason"], "soil_moisture_threshold_reached")
        self.assertEqual(stored_plan.status, "completed")
        self.assertEqual(stored_plan.execution_status, "stopped")
        self.assertEqual(stored_plan.execution_result["stop_reason"], "soil_moisture_threshold_reached")

    def test_stopped_plans_still_count_as_executed_in_analytics_and_reports(self):
        zone = list_zones(self.db)[0]
        plan = self._create_start_plan(zone.zone_id)
        approve_plan(self.db, plan.plan_id, actor="tester")
        execute_plan(self.db, plan.plan_id, actor="tester")
        manual_override_control(self.db, "stop", zone_id=zone.zone_id)

        funnel = get_plan_funnel(self.db)
        overview = get_analytics_overview(self.db)
        operations_csv = export_operations_report(self.db)
        zone_csv = export_zone_report(self.db, zone.zone_id)

        executed_stage = next(item for item in funnel["items"] if item["stage"] == "executed")
        completed_stage = next(item for item in funnel["items"] if item["stage"] == "completed_or_rejected")

        self.assertEqual(executed_stage["count"], 1)
        self.assertEqual(completed_stage["count"], 1)
        self.assertEqual(overview["kpis"]["executed_plan_count"], 1)
        self.assertIn("completed,approved,stopped", operations_csv)
        self.assertIn(",1,", zone_csv)


if __name__ == "__main__":
    unittest.main()
