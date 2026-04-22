import unittest
from unittest.mock import patch

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sklearn.tree import DecisionTreeClassifier as _DecisionTreeClassifier

    from src.database.models import Base, IrrigationPlan
    from src.services.decision_learning_service import recommend_plan_decision
    from src.services.irrigation_service import (
        _sensor_summary_cache,
        _weather_summary_cache,
        bootstrap_default_zones,
        collect_zone_evidence,
        create_plan,
        generate_plan_result,
        list_zones,
    )

    DEPS_AVAILABLE = True
except ModuleNotFoundError:
    DEPS_AVAILABLE = False


@unittest.skipUnless(DEPS_AVAILABLE, "SQLAlchemy / sklearn dependencies are not installed")
class TestDecisionLearningService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.SessionLocal()
        _sensor_summary_cache.clear()
        _weather_summary_cache.clear()
        bootstrap_default_zones(self.db)
        self.zone = list_zones(self.db)[0]
        self.zone.soil_moisture_threshold = 40
        self.zone.default_duration_minutes = 30
        self.db.commit()

    def tearDown(self):
        self.db.close()
        _sensor_summary_cache.clear()
        _weather_summary_cache.clear()

    def _historical_evidence(self, moisture: float, *, predicted: float | None = None, rain_expected: bool = False):
        predicted = moisture if predicted is None else predicted
        return {
            "zone": self.zone.to_dict(),
            "sensor_summary": {
                "status": "ok",
                "average": {"soil_moisture": moisture, "temperature": 22, "light_intensity": 220, "rainfall": 0},
            },
            "weather_summary": {"rain_expected": rain_expected},
            "ml_prediction": {
                "predicted_soil_moisture_24h": predicted,
                "fallback_used": False,
                "confidence": "medium",
                "sample_count": 10,
            },
        }

    def _insert_plan(self, moisture: float, action: str, duration: int, *, predicted: float | None = None, rain_expected: bool = False):
        plan = IrrigationPlan(
            zone_id=self.zone.zone_id,
            proposed_action=action,
            recommended_duration_minutes=duration,
            risk_level="medium" if rain_expected else "low",
            execution_status="executed" if action == "start" else "not_started",
            evidence_summary=self._historical_evidence(moisture, predicted=predicted, rain_expected=rain_expected),
        )
        self.db.add(plan)
        self.db.commit()
        return plan

    def _seed_decision_history(self):
        for moisture, action, duration in [
            (52, "hold", 0),
            (48, "hold", 0),
            (44, "hold", 0),
            (38, "start", 32),
            (34, "start", 38),
            (29, "start", 46),
            (42, "hold", 0),
            (36, "start", 36),
        ]:
            self._insert_plan(moisture, action, duration, predicted=moisture - 3)

    def test_falls_back_when_history_is_insufficient(self):
        evidence = collect_zone_evidence(self.db, self.zone)
        payload = recommend_plan_decision(
            self.db,
            zone_id=self.zone.zone_id,
            evidence=evidence,
            ml_prediction={"predicted_soil_moisture_24h": 35},
        )

        self.assertTrue(payload["fallback_used"])
        self.assertEqual(payload["sample_count"], 0)
        self.assertEqual(payload["recommended_action"], "hold")

    def test_recommends_from_historical_plans(self):
        self._seed_decision_history()
        with patch(
            "src.services.irrigation_service.DataCollectionModule.get_data",
            return_value={"data": {"soil_moisture": 35, "temperature": 22, "light_intensity": 220, "rainfall": 0}},
        ), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={"city": "北京", "forecast": [{"date": "2026-04-03", "dayweather": "晴", "daytemp": "28", "nighttemp": "18"}]},
        ):
            evidence = collect_zone_evidence(self.db, self.zone)

        payload = recommend_plan_decision(
            self.db,
            zone_id=self.zone.zone_id,
            evidence=evidence,
            ml_prediction={"predicted_soil_moisture_24h": 31, "fallback_used": False},
        )

        self.assertFalse(payload["fallback_used"])
        self.assertIn(payload["recommended_action"], {"start", "hold"})
        self.assertGreaterEqual(payload["recommended_duration_minutes"], 0)
        self.assertGreater(payload["sample_count"], 0)
        self.assertIn("top_factors", payload)

    def test_rain_hold_overrides_model_start(self):
        model_payload = {
            "recommended_action": "start",
            "recommended_duration_minutes": 45,
            "confidence": 1.0,
            "sample_count": 20,
            "model_type": "test_tree",
            "top_factors": ["soil_moisture"],
            "fallback_used": False,
        }
        with patch(
            "src.services.irrigation_service.DataCollectionModule.get_data",
            return_value={"data": {"soil_moisture": 32, "temperature": 20, "light_intensity": 120, "rainfall": 0}},
        ), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={"city": "北京", "forecast": [{"date": "2026-04-03", "dayweather": "小雨", "daytemp": "20", "nighttemp": "12"}]},
        ), patch(
            "src.services.irrigation_service.predict_zone_soil_moisture",
            return_value={"predicted_soil_moisture_24h": 20, "fallback_used": False},
        ), patch("src.services.irrigation_service.recommend_plan_decision", return_value=model_payload):
            result = generate_plan_result(self.db, self.zone.zone_id, trigger="test", requested_by="tester")

        suggestion = result["suggestion"]
        self.assertTrue(result["suggestion_only"])
        self.assertEqual(suggestion["proposed_action"], "hold")
        self.assertNotEqual(suggestion["recommended_duration_minutes"], model_payload["recommended_duration_minutes"])
        self.assertEqual(suggestion["evidence_summary"]["decision_model"], model_payload)

    def test_sensor_missing_overrides_model_start_and_records_reasoning(self):
        model_payload = {
            "recommended_action": "start",
            "recommended_duration_minutes": 45,
            "confidence": 1.0,
            "sample_count": 20,
            "model_type": "test_tree",
            "top_factors": ["sensor_ok"],
            "fallback_used": False,
        }
        with patch(
            "src.services.irrigation_service.DataCollectionModule.get_data",
            side_effect=RuntimeError("sensor offline"),
        ), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={"city": "北京", "forecast": [{"date": "2026-04-03", "dayweather": "晴", "daytemp": "20", "nighttemp": "12"}]},
        ), patch(
            "src.services.irrigation_service.predict_zone_soil_moisture",
            return_value={"predicted_soil_moisture_24h": 20, "fallback_used": False},
        ), patch("src.services.irrigation_service.recommend_plan_decision", return_value=model_payload):
            result = generate_plan_result(self.db, self.zone.zone_id, trigger="test", requested_by="tester")

        suggestion = result["suggestion"]
        self.assertTrue(result["suggestion_only"])
        self.assertEqual(suggestion["proposed_action"], "hold")
        self.assertIn("传感器数据缺失", suggestion["safety_review"]["blockers"])
        self.assertIn("decision_model", suggestion["evidence_summary"])
        self.assertIn("决策模型建议 start", suggestion["reasoning_summary"])


if __name__ == "__main__":
    unittest.main()
