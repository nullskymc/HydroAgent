import unittest

from src.llm.tool_argument_parser import ToolArgumentParserAgent


class TestToolArgumentParserAgent(unittest.TestCase):
    def setUp(self):
        self.parser = ToolArgumentParserAgent(llm=None)
        self.catalog = {
            "zones": [
                {"zone_id": "zone_alpha", "name": "分区 1", "ordinal": "1"},
                {"zone_id": "zone_beta", "name": "分区 2", "ordinal": "2"},
            ],
            "plans": [
                {"plan_id": "plan_abc123", "zone_id": "zone_alpha"},
            ],
        }

    def test_resolve_numeric_zone_ordinal(self):
        normalized = self.parser._normalize_locally(
            "query_sensor_data",
            {"zone_id": "2", "sensor_id": "primary"},
            self.catalog,
        )
        self.assertEqual(normalized["zone_id"], "zone_beta")

    def test_resolve_zone_name_alias(self):
        normalized = self.parser._normalize_locally(
            "query_weather",
            {"zone_id": "分区 2"},
            self.catalog,
        )
        self.assertEqual(normalized["zone_id"], "zone_beta")

    def test_keep_exact_zone_id(self):
        normalized = self.parser._normalize_locally(
            "query_sensor_data",
            {"zone_id": "zone_alpha"},
            self.catalog,
        )
        self.assertEqual(normalized["zone_id"], "zone_alpha")

    def test_resolve_plan_prefix_when_clear(self):
        normalized = self.parser._normalize_locally(
            "get_plan_status",
            {"plan_id": "plan_abc"},
            self.catalog,
        )
        self.assertEqual(normalized["plan_id"], "plan_abc123")


if __name__ == "__main__":
    unittest.main()
