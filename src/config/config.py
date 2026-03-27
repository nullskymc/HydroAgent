"""
配置管理模块 - 负责加载和提供配置信息
"""
import os
import yaml
import logging
from dotenv import load_dotenv

class Config:
    """
    配置管理类，从环境变量、YAML文件等加载配置。
    """
    def __init__(self, config_file_path=None, env_file_path=None):
        """
        初始化配置管理器。
        :param config_file_path: YAML配置文件路径 (可选)
        :param env_file_path: 环境变量文件路径 (可选, 默认为根目录下的.env)
        """
        # 加载环境变量
        if env_file_path:
            load_dotenv(env_file_path)
        else:
            load_dotenv()  # 默认加载根目录下的.env文件
            
        # 优先加载 config.yaml
        config_path = config_file_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../config.yaml')
        self._config_from_yaml = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config_from_yaml = yaml.safe_load(f) or {}
        
        # 数据库配置 - 优先从环境变量读取
        self.DB_HOST = os.getenv('DB_HOST') or self._config_from_yaml.get('database', {}).get('host', 'localhost')
        self.DB_PORT = int(os.getenv('DB_PORT') or self._config_from_yaml.get('database', {}).get('port', 5432))
        self.DB_NAME = os.getenv('DB_NAME') or self._config_from_yaml.get('database', {}).get('name', 'irrigation_db')
        self.DB_USER = os.getenv('DB_USER') or self._config_from_yaml.get('database', {}).get('user', 'postgres')
        self.DB_PASSWORD = os.getenv('DB_PASSWORD') or self._config_from_yaml.get('database', {}).get('password', 'postgres')
        self.DB_TYPE = os.getenv('DB_TYPE') or self._config_from_yaml.get('database', {}).get('type', 'sqlite')
        
        # API密钥
        self.WEATHER_API_KEY = os.getenv("WEATHER_API_KEY") or self._get_from_yaml("apis.weather_api_key", "")
        self.API_SERVICE_URL = os.getenv("API_SERVICE_URL") or self._get_from_yaml(
            "apis.weather_service_url", "https://api.openweathermap.org/data/2.5/weather")
        
        # 传感器配置
        self.SENSOR_IDS = os.getenv("SENSOR_IDS") and os.getenv("SENSOR_IDS").split(",") or self._get_from_yaml("sensors.ids", ["sensor_001", "sensor_002"])
        self.DATA_COLLECTION_INTERVAL_MINUTES = int(os.getenv("DATA_COLLECTION_INTERVAL") or self._get_from_yaml(
            "sensors.collection_interval_minutes", 5))
        
        # 灌溉策略
        soil_threshold = os.getenv("SOIL_MOISTURE_THRESHOLD") or self._get_from_yaml("irrigation_strategy.soil_moisture_threshold", 30.0)
        duration_mins = os.getenv("DEFAULT_IRRIGATION_DURATION") or self._get_from_yaml("irrigation_strategy.default_duration_minutes", 30)
        
        self.IRRIGATION_STRATEGY = {
            "soil_moisture_threshold": float(soil_threshold),
            "default_duration_minutes": int(duration_mins)
        }
        
        # 模型配置
        self.MODEL_PATH = os.getenv("MODEL_PATH") or self._get_from_yaml("ml_model.path", None)
        self.MODEL_INPUT_SIZE = int(os.getenv("MODEL_INPUT_SIZE") or self._get_from_yaml("ml_model.input_size", 6))
        self.MODEL_HIDDEN_SIZE = int(os.getenv("MODEL_HIDDEN_SIZE") or self._get_from_yaml("ml_model.hidden_size", 50))
        # 新增：模型名称配置
        self.MODEL_NAME = self._config_from_yaml.get('model_name') or os.getenv('MODEL_NAME') or 'gpt-4o'
        
        # 报警配置
        self.ALARM_THRESHOLD_SOIL_MOISTURE = float(os.getenv("ALARM_THRESHOLD") or self._get_from_yaml(
            "alarm.soil_moisture_threshold", 25.0))
        self.ALARM_ENABLED = os.getenv("ALARM_ENABLED", "true").lower() == "true" or self._get_from_yaml("alarm.enabled", True)
        
        # 日志配置
        self.LOG_LEVEL = os.getenv("LOG_LEVEL") or self._get_from_yaml("logging.level", "INFO")
        self.LOG_FILE = os.getenv("LOG_FILE") or self._get_from_yaml("logging.file", "irrigation_system.log")
        
        # LLM/OPENAI配置
        self.OPENAI_API_KEY = (
            self._config_from_yaml.get('openai_api_key')
            or os.getenv('OPENAI_API_KEY')
        )
        self.OPENAI_BASE_URL = (
            self._config_from_yaml.get('openai_base_url')
            or os.getenv('OPENAI_BASE_URL')
        )
        
        # FastAPI 服务配置
        self.APP_HOST = os.getenv('APP_HOST') or self._get_from_yaml('app.host', '0.0.0.0')
        self.APP_PORT = int(os.getenv('APP_PORT') or self._get_from_yaml('app.port', 7860))
        
        # MCP Server 路径
        self.MCP_SERVER_PATH = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '../mcp_server.py'
        )
    
    def _get_from_yaml(self, path, default=None):
        """
        从嵌套的YAML配置中提取值
        :param path: 以点分隔的配置路径 (例如 "database.host")
        :param default: 如果找不到值，返回的默认值
        :return: 配置值或默认值
        """
        keys = path.split('.')
        value = self._config_from_yaml
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def get_db_uri(self):
        """
        返回数据库连接URI字符串。
        根据 DB_TYPE 动态生成，支持 sqlite (默认), mysql, postgresql。
        """
        db_type = self.DB_TYPE.lower()
        if db_type == "postgresql":
            return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        elif db_type == "mysql":
            return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        else:
            # 默认 SQLite —— 零配置启动
            db_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), f'../../{self.DB_NAME}.db'
            )
            return f"sqlite:///{os.path.abspath(db_path)}"

# 全局配置实例 - 单例模式
config = Config()