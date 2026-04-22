"""
数据采集模块的测试
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from src.data.data_collection import DataCollectionModule
from src.exceptions.exceptions import InvalidSensorDataError

class TestDataCollectionModule(unittest.TestCase):
    """测试数据采集模块"""
    
    def setUp(self):
        """测试前准备"""
        self.sensor_ids = ["test-sensor-1", "test-sensor-2"]
        self.collection_module = DataCollectionModule(sensor_ids=self.sensor_ids)
    
    def test_init(self):
        """测试初始化"""
        # 验证传感器ID正确设置
        self.assertEqual(self.collection_module.sensor_ids, self.sensor_ids)
        
        # 测试默认配置
        with patch('src.data.data_collection.config') as mock_config:
            mock_config.SENSOR_IDS = ["default-sensor-1"]
            module = DataCollectionModule()
            self.assertEqual(module.sensor_ids, ["default-sensor-1"])
    
    def test_get_data(self):
        """测试数据获取"""
        # 获取数据
        data = self.collection_module.get_data()
        
        # 验证数据结构
        self.assertIn("timestamp", data)
        self.assertIn("sensor_id", data)
        self.assertIn("data", data)
        
        # 验证传感器ID是否在预定义列表中
        self.assertIn(data["sensor_id"], self.sensor_ids)
        
        # 验证数据字段
        sensor_data = data["data"]
        self.assertIn("soil_moisture", sensor_data)
        self.assertIn("temperature", sensor_data)
        self.assertIn("light_intensity", sensor_data)
        self.assertIn("rainfall", sensor_data)
        
        # 验证数据类型和范围
        self.assertIsInstance(sensor_data["soil_moisture"], float)
        self.assertGreaterEqual(sensor_data["soil_moisture"], 0)
        self.assertLessEqual(sensor_data["soil_moisture"], 100)
    
    @patch('src.data.data_collection.random.choice')
    def test_get_data_error(self, mock_choice):
        """测试数据获取错误处理"""
        # 模拟random.choice抛出异常
        mock_choice.side_effect = Exception("测试异常")
        
        # 验证异常被正确抛出和转换
        with self.assertRaises(InvalidSensorDataError):
            self.collection_module.get_data()
    
    @patch('src.data.data_collection.DataCollectionModule.get_data')
    def test_collect_and_store(self, mock_get_data):
        """测试数据采集和存储"""
        # 模拟get_data的返回值
        mock_data = {
            "timestamp": datetime.now().isoformat(),
            "sensor_id": "test-sensor-1",
            "data": {
                "soil_moisture": 50.0,
                "temperature": 25.0,
                "light_intensity": 800.0,
                "rainfall": 0.0
            }
        }
        mock_get_data.return_value = mock_data
        
        # 创建模拟数据库会话
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        
        # 调用测试方法
        result = self.collection_module.collect_and_store(mock_db)
        
        # 验证返回值
        self.assertEqual(result, mock_data)
        
        # 验证数据库操作
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        
        # 测试没有数据库会话的情况
        result_no_db = self.collection_module.collect_and_store()
        self.assertEqual(result_no_db, mock_data)

if __name__ == "__main__":
    unittest.main()
