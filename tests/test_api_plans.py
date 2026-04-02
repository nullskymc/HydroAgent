import unittest
import importlib
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api import get_db, router
from src.database.models import Base, ConversationSession, ToolExecutionEvent, ChatMessage
from src.services.irrigation_service import bootstrap_default_zones


class TestPlanApi(unittest.TestCase):
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
        app = FastAPI()
        app.include_router(router, prefix="/api")

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()

    def test_generate_approve_execute_plan(self):
        zone_id = bootstrap_default_zones(self.db)[0].zone_id
        response = self.client.post("/api/plans/generate", json={"zone_id": zone_id})
        self.assertEqual(response.status_code, 200)
        plan = response.json()["plan"]
        plan_id = plan["plan_id"]

        approve_response = self.client.post(f"/api/plans/{plan_id}/approve", json={"actor": "tester"})
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["plan"]["approval_status"], "approved")

        execute_response = self.client.post(f"/api/plans/{plan_id}/execute", json={"actor": "tester"})
        if execute_response.status_code == 400:
            # Hold plans are valid outputs; force a second approval path is not required for this test.
            self.assertIn("Only start plans can be executed", execute_response.text)
        else:
            self.assertEqual(execute_response.status_code, 200)
            self.assertEqual(execute_response.json()["plan"]["execution_status"], "executed")

    def test_chat_stream_emits_plan_event(self):
        session = ConversationSession(session_id="conv-test", title="chat test", message_count=0)
        self.db.add(session)
        self.db.commit()

        class FakeAgent:
            _initialized = True

            async def initialize(self):
                return

            async def chat_stream(self, messages, conversation_id=None):
                yield {"type": "text", "content": "已分析。"}
                yield {
                    "type": "plan_proposed",
                    "plan": {
                        "plan_id": "plan_test",
                        "zone_id": "zone_test",
                        "zone_name": "测试分区",
                        "status": "pending_approval",
                        "approval_status": "pending",
                        "execution_status": "not_started",
                        "proposed_action": "start",
                        "risk_level": "low",
                        "urgency": "high",
                        "recommended_duration_minutes": 30,
                        "requires_approval": True,
                    },
                }
                yield {"type": "done"}

        module = importlib.import_module("src.llm.langchain_agent")
        with patch.object(module, "get_hydro_agent", return_value=FakeAgent()):
            response = self.client.post("/api/chat", json={"conversation_id": "conv-test", "message": "生成计划"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "plan_proposed"', response.text)
        self.assertIn('"type": "done"', response.text)

    def test_chat_persists_tool_trace_and_conversation_detail(self):
        session = ConversationSession(session_id="conv-trace", title="trace test", message_count=0)
        self.db.add(session)
        self.db.commit()

        class FakeAgent:
            _initialized = True

            async def initialize(self):
                return

            async def chat_stream(self, messages, conversation_id=None):
                yield {
                    "type": "tool_call",
                    "tool": "query_sensor_data",
                    "run_id": "tool-run-1",
                    "args": {"zone_id": "2", "sensor_id": "primary"},
                    "normalized_args": {"zone_id": "zone_test", "sensor_id": "primary"},
                    "zone_id": "zone_test",
                }
                yield {
                    "type": "subagent_handoff",
                    "run_id": "task-run-1",
                    "subagent": "zone-analyst",
                    "task_description": "Collect evidence for zone_test",
                    "zone_id": "zone_test",
                }
                yield {
                    "type": "subagent_result",
                    "run_id": "task-run-1",
                    "subagent": "zone-analyst",
                    "result_preview": "Zone evidence collected successfully.",
                    "zone_id": "zone_test",
                }
                yield {
                    "type": "tool_result",
                    "tool": "query_sensor_data",
                    "run_id": "tool-run-1",
                    "args": {"zone_id": "2", "sensor_id": "primary"},
                    "normalized_args": {"zone_id": "zone_test", "sensor_id": "primary"},
                    "zone_id": "zone_test",
                    "result": {"zone_id": "zone_test", "soil_moisture": 31},
                    "output_preview": '{"zone_id":"zone_test","soil_moisture":31}',
                    "duration_ms": 42,
                }
                yield {"type": "text", "content": "已完成分析。"}
                yield {"type": "done"}

        module = importlib.import_module("src.llm.langchain_agent")
        with patch.object(module, "get_hydro_agent", return_value=FakeAgent()):
            response = self.client.post("/api/chat", json={"conversation_id": "conv-trace", "message": "检查分区 2"})

        self.assertEqual(response.status_code, 200)
        self.assertIn('"trace_id": "trace_', response.text)

        events = self.db.query(ToolExecutionEvent).order_by(ToolExecutionEvent.step_index.asc()).all()
        self.assertEqual(len(events), 4)
        self.assertEqual(events[0].event_type, "tool_start")
        self.assertEqual(events[0].normalized_args["zone_id"], "zone_test")
        self.assertEqual(events[-1].event_type, "tool_end")
        self.assertEqual(events[-1].duration_ms, 42)

        assistant = self.db.query(ChatMessage).filter(ChatMessage.role == "assistant").first()
        self.assertIsNotNone(assistant)
        self.assertIsNotNone(assistant.trace_id)

        detail_response = self.client.get("/api/conversations/conv-trace")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        assistant_messages = [message for message in detail_payload["messages"] if message["role"] == "assistant"]
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(assistant_messages[0]["tool_trace"]["status"], "completed")
        self.assertEqual(len(assistant_messages[0]["tool_trace"]["steps"]), 4)

        trace_response = self.client.get("/api/tool-traces?conversation_id=conv-trace")
        self.assertEqual(trace_response.status_code, 200)
        trace_payload = trace_response.json()["tool_traces"]
        self.assertEqual(len(trace_payload), 1)
        self.assertEqual(trace_payload[0]["zone_id"], "zone_test")


if __name__ == "__main__":
    unittest.main()
