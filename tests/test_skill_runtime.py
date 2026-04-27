import unittest

from src.llm.skill_runtime import HydroSkillRuntime


class TestHydroSkillRuntime(unittest.TestCase):
    def setUp(self):
        self.runtime = HydroSkillRuntime()

    def test_planner_lifecycle_skill_keeps_evidence_tools(self):
        context = self.runtime.resolve_for_chat(
            mode="planner",
            message="【Agent核心测试】为 soil moisture 最低的分区生成灌溉建议或计划，说明证据、风险和审批要求。",
        )

        self.assertIn("system-plan-lifecycle", context.active_skill_ids)
        self.assertIn("query_sensor_data", context.allowed_tools)
        self.assertIn("query_weather", context.allowed_tools)
        self.assertIn("predict_soil_moisture", context.allowed_tools)
        self.assertIn("create_irrigation_plan", context.allowed_tools)
        self.assertIn("get_plan_status", context.allowed_tools)
        self.assertNotIn("approve_irrigation_plan", context.allowed_tools)
        self.assertNotIn("execute_approved_plan", context.allowed_tools)

    def test_skill_tools_are_prioritized_without_crossing_mode_boundary(self):
        context = self.runtime.resolve_for_chat(
            mode="planner",
            message="请检查计划审批状态并说明为什么不能执行。",
            explicit_skill_ids=["system-plan-lifecycle"],
        )

        self.assertEqual(context.allowed_tools[0], "create_irrigation_plan")
        self.assertIn("query_sensor_data", context.allowed_tools)
        self.assertNotIn("approve_irrigation_plan", context.allowed_tools)
        self.assertNotIn("execute_approved_plan", context.allowed_tools)


if __name__ == "__main__":
    unittest.main()
