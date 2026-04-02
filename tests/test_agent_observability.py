import asyncio
import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.llm.langchain_agent as agent_module
from src.database.models import AgentDecisionLog, Base
from src.llm.langchain_agent import HydroDeepAgent


class FakeCompiledDeepAgent:
    async def astream_events(self, input_data, config=None, version=None):
        yield {
            "event": "on_tool_start",
            "name": "task",
            "run_id": "task-run-1",
            "data": {
                "input": {
                    "subagent_type": "zone-analyst",
                    "description": "Collect evidence for zone_id zone_test and related plan_id plan_test.",
                }
            },
        }
        yield {
            "event": "on_tool_end",
            "name": "task",
            "run_id": "task-run-1",
            "data": {"output": "Zone evidence collected successfully."},
        }
        yield {
            "event": "on_tool_end",
            "name": "create_irrigation_plan",
            "run_id": "tool-run-2",
            "data": {
                "output": json.dumps(
                    {
                        "plan_id": "plan_test",
                        "zone_id": "zone_test",
                        "zone_name": "测试分区",
                        "status": "pending_approval",
                        "approval_status": "pending",
                        "execution_status": "not_started",
                        "proposed_action": "start",
                        "risk_level": "low",
                        "recommended_duration_minutes": 20,
                        "requires_approval": True,
                    },
                    ensure_ascii=False,
                )
            },
        }


class TestAgentObservability(unittest.TestCase):
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
        self.original_session_local = agent_module.SessionLocal
        agent_module.SessionLocal = self.SessionLocal

    def tearDown(self):
        agent_module.SessionLocal = self.original_session_local

    def test_chat_stream_emits_subagent_events_and_persists_logs(self):
        hydro_agent = HydroDeepAgent()
        hydro_agent._initialized = True
        hydro_agent._agent = FakeCompiledDeepAgent()

        async def collect_events():
            return [
                event
                async for event in hydro_agent.chat_stream(
                    [{"role": "user", "content": "为 zone_test 生成灌溉计划"}],
                    conversation_id="conv-observe",
                )
            ]

        events = asyncio.run(collect_events())
        event_types = [event["type"] for event in events]

        self.assertIn("subagent_handoff", event_types)
        self.assertIn("subagent_result", event_types)
        self.assertIn("plan_proposed", event_types)
        self.assertEqual(event_types[-1], "done")

        db = self.SessionLocal()
        try:
            logs = db.query(AgentDecisionLog).order_by(AgentDecisionLog.created_at.asc()).all()
            self.assertEqual(len(logs), 2)
            self.assertEqual(logs[0].decision_result["subagent"], "zone-analyst")
            self.assertEqual(logs[0].decision_result["status"], "started")
            self.assertEqual(logs[0].zone_id, "zone_test")
            self.assertEqual(logs[0].plan_id, "plan_test")
            self.assertEqual(logs[1].decision_result["status"], "completed")
            self.assertIn("Zone evidence collected", logs[1].decision_result["result_preview"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
