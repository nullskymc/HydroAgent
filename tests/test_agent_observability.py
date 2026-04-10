import unittest
from unittest.mock import patch

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.database.models import AlertEvent, AuditEvent, Base
    from src.services.alert_service import acknowledge_alert, evaluate_alerts, resolve_alert
    from src.services.auth_service import ensure_auth_seed, record_audit_event
    from src.services.irrigation_service import bootstrap_default_zones
    from src.services.irrigation_service import _sensor_summary_cache, _weather_summary_cache

    DEPS_AVAILABLE = True
except ModuleNotFoundError:
    DEPS_AVAILABLE = False


@unittest.skipUnless(DEPS_AVAILABLE, "SQLAlchemy dependencies are not installed")
class TestAdminObservability(unittest.TestCase):
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
        _sensor_summary_cache.clear()
        _weather_summary_cache.clear()
        bootstrap_default_zones(self.db)
        ensure_auth_seed(self.db)

    def tearDown(self):
        self.db.close()

    def test_alert_generation_acknowledge_and_resolve(self):
        with patch("src.services.irrigation_service.DataCollectionModule.get_data", return_value={"data": {"soil_moisture": 8, "temperature": 22, "light_intensity": 180, "rainfall": 0}}), patch(
            "src.services.irrigation_service.DataProcessingModule.get_weather_by_city_name",
            return_value={
                "city": "北京",
                "forecast": [
                    {"date": "2026-04-03", "dayweather": "晴", "daytemp": "28", "nighttemp": "18"}
                ],
            },
        ):
            evaluate_alerts(self.db)

        alert = self.db.query(AlertEvent).first()
        self.assertIsNotNone(alert)
        acknowledged = acknowledge_alert(self.db, alert.alert_id, "operator")
        self.assertEqual(acknowledged.status, "acknowledged")
        resolved = resolve_alert(self.db, alert.alert_id, "operator")
        self.assertEqual(resolved.status, "resolved")

    def test_audit_event_persists_admin_actions(self):
        event = record_audit_event(
            self.db,
            actor="admin",
            event_type="user.update",
            object_type="user",
            object_id="1",
            details={"field": "is_active"},
        )
        stored = self.db.query(AuditEvent).filter(AuditEvent.audit_id == event.audit_id).first()
        self.assertIsNotNone(stored)
        self.assertEqual(stored.actor, "admin")
        self.assertEqual(stored.event_type, "user.update")


if __name__ == "__main__":
    unittest.main()
