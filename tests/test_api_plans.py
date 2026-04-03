import unittest
from unittest.mock import patch

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.api import get_db as api_get_db, router as api_router
    from src.database.models import Base, get_db as model_get_db
    from src.routers.alert_router import router as alert_router
    from src.routers.analytics_router import router as analytics_router
    from src.routers.asset_router import router as asset_router
    from src.routers.auth_router import router as auth_router
    from src.routers.knowledge_router import router as knowledge_router
    from src.routers.report_router import router as report_router
    from src.routers.user_router import router as user_router
    from src.services.alert_service import evaluate_alerts
    from src.services.auth_service import ensure_auth_seed
    from src.services.irrigation_service import bootstrap_default_zones

    DEPS_AVAILABLE = True
except ModuleNotFoundError:
    DEPS_AVAILABLE = False


@unittest.skipUnless(DEPS_AVAILABLE, "FastAPI / SQLAlchemy dependencies are not installed")
class TestAdminApi(unittest.TestCase):
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
        ensure_auth_seed(self.db)
        app = FastAPI()
        app.include_router(api_router, prefix="/api")
        app.include_router(auth_router, prefix="/api")
        app.include_router(user_router, prefix="/api")
        app.include_router(asset_router, prefix="/api")
        app.include_router(knowledge_router, prefix="/api")
        app.include_router(alert_router, prefix="/api")
        app.include_router(analytics_router, prefix="/api")
        app.include_router(report_router, prefix="/api")

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[api_get_db] = override_get_db
        app.dependency_overrides[model_get_db] = override_get_db
        self.client = TestClient(app)
        login_response = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login_response.status_code, 200)
        self.token = login_response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.db.close()

    def test_login_and_fetch_profile(self):
        response = self.client.get("/api/auth/me", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("admin", response.json()["user"]["roles"])

    def test_user_and_role_endpoints(self):
        users_response = self.client.get("/api/users", headers=self.headers)
        roles_response = self.client.get("/api/roles", headers=self.headers)
        self.assertEqual(users_response.status_code, 200)
        self.assertEqual(roles_response.status_code, 200)
        self.assertGreaterEqual(len(users_response.json()["users"]), 1)
        self.assertGreaterEqual(len(roles_response.json()["roles"]), 5)

    def test_asset_and_analytics_endpoints(self):
        assets_response = self.client.get("/api/assets/zones", headers=self.headers)
        analytics_response = self.client.get("/api/analytics/overview?range=7d", headers=self.headers)
        self.assertEqual(assets_response.status_code, 200)
        self.assertEqual(analytics_response.status_code, 200)
        self.assertIn("kpis", analytics_response.json())

    def test_alert_and_report_endpoints(self):
        with patch("src.services.irrigation_service.DataCollectionModule.get_data", return_value={"data": {"soil_moisture": 10, "temperature": 22, "light_intensity": 180, "rainfall": 0}}):
            evaluate_alerts(self.db)
        alerts_response = self.client.get("/api/alerts", headers=self.headers)
        report_response = self.client.get("/api/reports/operations/export", headers=self.headers)
        self.assertEqual(alerts_response.status_code, 200)
        self.assertEqual(report_response.status_code, 200)
        self.assertIn("zone_id", report_response.text)

    def test_settings_never_return_plaintext_keys(self):
        update_response = self.client.put(
            "/api/settings",
            headers=self.headers,
            json={
                "model_name": "gpt-4o-mini",
                "openai_api_key": "sk-test-secret",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        payload = update_response.json()["settings"]
        self.assertEqual(payload["model_name"], "gpt-4o-mini")
        self.assertTrue(payload["openai_api_key_status"]["configured"])
        self.assertNotIn("sk-test-secret", str(payload))

    def test_knowledge_document_endpoints(self):
        class FakeCollection:
            def __init__(self):
                self.ids = []

            def upsert(self, ids, documents, embeddings, metadatas):
                self.ids.extend(ids)

            def delete(self, ids):
                self.ids = [item for item in self.ids if item not in ids]

            def count(self):
                return len(self.ids)

            def query(self, **kwargs):
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        with patch("src.knowledge.service.KnowledgeBaseService._get_collection", return_value=FakeCollection()):
            with patch("src.knowledge.service.KnowledgeBaseService._embed_texts", return_value=[[0.1, 0.2]]):
                create_response = self.client.post(
                    "/api/knowledge/documents",
                    headers=self.headers,
                    json={
                        "title": "Pump SOP",
                        "content": "Maintain pressure valves weekly.",
                        "source_uri": "https://example.com/sop",
                    },
                )
                self.assertEqual(create_response.status_code, 200)
                document_id = create_response.json()["document"]["document_id"]

                list_response = self.client.get("/api/knowledge/documents?page=1&page_size=10", headers=self.headers)
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(list_response.json()["pagination"]["total"], 1)

                detail_response = self.client.get(f"/api/knowledge/documents/{document_id}", headers=self.headers)
                self.assertEqual(detail_response.status_code, 200)
                self.assertEqual(detail_response.json()["document"]["document_id"], document_id)


if __name__ == "__main__":
    unittest.main()
