import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import src.llm.persistence as persistence_module

    DEPS_AVAILABLE = True
except ModuleNotFoundError:
    DEPS_AVAILABLE = False


@unittest.skipUnless(DEPS_AVAILABLE, "LangGraph SQLite persistence dependencies are not installed")
class TestChatPlanPersistence(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.workspace_dir = Path(self.tempdir.name)
        self.db_path = self.workspace_dir / "langgraph-persistence.sqlite"
        self.workspace_patcher = patch.object(persistence_module, "WORKSPACE_DIR", self.workspace_dir)
        self.db_path_patcher = patch.object(persistence_module, "PERSISTENCE_DB_PATH", self.db_path)
        self.workspace_patcher.start()
        self.db_path_patcher.start()
        self.persistence = persistence_module.HydroGraphPersistence()
        await self.persistence.initialize()
        await self.persistence.ensure_thread("conv-1", title="测试会话")

    async def asyncTearDown(self):
        await self.persistence.close()
        self.db_path_patcher.stop()
        self.workspace_patcher.stop()
        self.tempdir.cleanup()

    async def test_get_conversation_rehydrates_single_latest_plan_card(self):
        await self.persistence.record_plan_event(
            "conv-1",
            {
                "event_id": "planevt-1",
                "event_type": "plan_proposed",
                "plan_id": "plan_123",
                "trace_id": "trace_1",
                "created_at": "2026-04-03T10:00:01+00:00",
                "plan": {
                    "plan_id": "plan_123",
                    "zone_id": "zone_1",
                    "conversation_id": "conv-1",
                    "status": "pending_approval",
                    "approval_status": "pending",
                    "execution_status": "not_started",
                    "proposed_action": "start",
                    "risk_level": "medium",
                    "recommended_duration_minutes": 20,
                },
            },
        )
        await self.persistence.record_plan_event(
            "conv-1",
            {
                "event_id": "planevt-2",
                "event_type": "approval_result",
                "plan_id": "plan_123",
                "trace_id": None,
                "created_at": "2026-04-03T10:05:00+00:00",
                "plan": {
                    "plan_id": "plan_123",
                    "zone_id": "zone_1",
                    "conversation_id": "conv-1",
                    "status": "approved",
                    "approval_status": "approved",
                    "execution_status": "not_started",
                    "proposed_action": "start",
                    "risk_level": "medium",
                    "recommended_duration_minutes": 20,
                },
            },
        )
        await self.persistence.record_chat_turn(
            "conv-1",
            trace_id="trace_1",
            user_content="给 1 号分区生成计划",
            assistant_content="已生成计划，请审批。",
        )

        payload = await self.persistence.get_conversation("conv-1")

        self.assertIsNotNone(payload)
        messages = payload["messages"]
        plan_messages = [message for message in messages if message.get("plan")]

        self.assertEqual([message["role"] for message in messages], ["user", "tool", "assistant"])
        self.assertEqual(len(plan_messages), 1)
        self.assertEqual(plan_messages[0]["plan"]["plan_id"], "plan_123")
        self.assertEqual(plan_messages[0]["plan"]["approval_status"], "approved")

    async def test_get_conversation_keeps_distinct_plan_cards(self):
        await self.persistence.record_plan_event(
            "conv-1",
            {
                "event_id": "planevt-3",
                "event_type": "suggestion_result",
                "suggestion_id": "suggestion_a",
                "trace_id": "trace_2",
                "created_at": "2026-04-03T11:00:01+00:00",
                "suggestion": {
                    "suggestion_id": "suggestion_a",
                    "zone_id": "zone_a",
                    "conversation_id": "conv-1",
                    "proposed_action": "hold",
                    "risk_level": "low",
                    "urgency": "normal",
                    "recommended_duration_minutes": 0,
                },
            },
        )
        await self.persistence.record_plan_event(
            "conv-1",
            {
                "event_id": "planevt-4",
                "event_type": "plan_proposed",
                "plan_id": "plan_b",
                "trace_id": "trace_2",
                "created_at": "2026-04-03T11:00:02+00:00",
                "plan": {
                    "plan_id": "plan_b",
                    "zone_id": "zone_b",
                    "conversation_id": "conv-1",
                    "status": "pending_approval",
                    "approval_status": "pending",
                    "execution_status": "not_started",
                    "proposed_action": "start",
                    "risk_level": "medium",
                    "recommended_duration_minutes": 15,
                },
            },
        )
        await self.persistence.record_chat_turn(
            "conv-1",
            trace_id="trace_2",
            user_content="为所有分区生成计划",
            assistant_content="已按分区生成结构化计划。",
        )

        payload = await self.persistence.get_conversation("conv-1")

        self.assertIsNotNone(payload)
        plan_ids = [message["plan"]["plan_id"] for message in payload["messages"] if message.get("plan")]
        suggestion_ids = [message["suggestion"]["suggestion_id"] for message in payload["messages"] if message.get("suggestion")]
        self.assertEqual(plan_ids, ["plan_b"])
        self.assertEqual(suggestion_ids, ["suggestion_a"])


if __name__ == "__main__":
    unittest.main()
