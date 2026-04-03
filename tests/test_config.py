"""
配置管理模块的测试
"""
import os
import unittest
import tempfile
import yaml
from src.config import Config

class TestConfig(unittest.TestCase):
    """测试配置管理模块"""
    
    def setUp(self):
        """测试前准备工作"""
        # 创建测试用的临时YAML配置文件
        self.config_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml')
        yaml_content = {
            "database": {
                "host": "test-db-host",
                "port": 5678,
                "name": "test-db-name",
                "user": "test-db-user",
                "password": "test-db-password",
                "type": "postgresql"
            },
            "apis": {
                "weather_api_key": "test-api-key",
                "weather_service_url": "http://test-api.example.com"
            },
            "sensors": {
                "ids": ["test-sensor-001", "test-sensor-002"],
                "collection_interval_minutes": 10
            }
        }
        yaml.dump(yaml_content, self.config_file)
        self.config_file.close()
        
        # 备份当前环境变量
        self.original_env = os.environ.copy()
        
        # 设置测试环境变量
        os.environ["DB_HOST"] = "env-db-host"
        os.environ["WEATHER_API_KEY"] = "env-api-key"
    
    def tearDown(self):
        """测试后清理工作"""
        # 删除临时文件
        os.unlink(self.config_file.name)
        
        # 恢复原始环境变量
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_config_load_from_yaml(self):
        """测试从YAML文件加载配置"""
        config = Config(config_file_path=self.config_file.name)
        
        # 验证从YAML加载的配置
        self.assertEqual(config.DB_HOST, "env-db-host")  # 环境变量优先
        self.assertEqual(config.DB_PORT, 5678)  # 从YAML加载
        self.assertEqual(config.DB_NAME, "test-db-name")
        self.assertEqual(config.SENSOR_IDS, ["test-sensor-001", "test-sensor-002"])
    
    def test_config_priority(self):
        """测试配置加载优先级：环境变量 > YAML > 默认值"""
        config = Config(config_file_path=self.config_file.name)
        
        # 环境变量优先
        self.assertEqual(config.WEATHER_API_KEY, "env-api-key")
        
        # 删除环境变量，应该回退到YAML值
        del os.environ["WEATHER_API_KEY"]
        del os.environ["DB_HOST"]
        config = Config(config_file_path=self.config_file.name)
        self.assertEqual(config.WEATHER_API_KEY, "test-api-key")
        self.assertEqual(config.DB_HOST, "test-db-host")
        
        # 如果YAML中也没有，应该使用默认值
        test_config = {
            "database": {"host": "yaml-host"}
        }
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml') as minimal_config:
            yaml.dump(test_config, minimal_config)
        
        config = Config(config_file_path=minimal_config.name)
        self.assertEqual(config.DB_HOST, "yaml-host")  # 从YAML加载
        self.assertEqual(config.DB_PORT, 5432)  # 使用默认值
        
        os.unlink(minimal_config.name)
    
    def test_get_db_uri(self):
        """测试数据库URI生成"""
        os.environ["DB_TYPE"] = "postgresql"
        config = Config(config_file_path=self.config_file.name)
        expected_uri = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        self.assertEqual(config.get_db_uri(), expected_uri)
        # 测试其他数据库类型
        os.environ["DB_TYPE"] = "mysql"
        config = Config(config_file_path=self.config_file.name)
        expected_uri = f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        self.assertEqual(config.get_db_uri(), expected_uri)

    def test_secret_settings_are_masked_in_runtime_snapshot(self):
        """测试敏感配置仅以掩码状态暴露给前端。"""
        config = Config(config_file_path=self.config_file.name)
        config.update_runtime_settings({
            "openai_api_key": "sk-secret-demo",
            "embedding_api_key": "sk-embed-demo",
        })

        runtime = config.get_runtime_settings()
        self.assertTrue(runtime["openai_api_key_status"]["configured"])
        self.assertTrue(runtime["embedding_api_key_status"]["configured"])
        self.assertNotIn("sk-secret-demo", str(runtime))
        self.assertNotIn("sk-embed-demo", str(runtime))

if __name__ == "__main__":
    unittest.main()
