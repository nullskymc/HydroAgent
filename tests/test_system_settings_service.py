import unittest

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.database.models import Base
    from src.services.system_settings_service import ensure_system_settings, get_system_settings_snapshot, update_system_settings

    DEPS_AVAILABLE = True
except ModuleNotFoundError:
    DEPS_AVAILABLE = False


@unittest.skipUnless(DEPS_AVAILABLE, "SQLAlchemy dependencies are not installed")
class TestSystemSettingsService(unittest.TestCase):
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

    def tearDown(self):
        self.db.close()

    def test_ensure_system_settings_bootstraps_singleton(self):
        settings = ensure_system_settings(self.db)
        snapshot = get_system_settings_snapshot(self.db)

        self.assertEqual(settings.singleton_key, "default")
        self.assertIn("default_soil_moisture_threshold", snapshot)
        self.assertIn("knowledge_chunk_size", snapshot)

    def test_update_system_settings_changes_business_defaults_only(self):
        ensure_system_settings(self.db)
        snapshot = update_system_settings(
            self.db,
            {
                "soil_moisture_threshold": 46,
                "default_duration_minutes": 22,
                "alarm_enabled": False,
            },
        )

        self.assertEqual(snapshot["default_soil_moisture_threshold"], 46.0)
        self.assertEqual(snapshot["default_duration_minutes"], 22)
        self.assertFalse(snapshot["alarm_enabled"])


if __name__ == "__main__":
    unittest.main()
