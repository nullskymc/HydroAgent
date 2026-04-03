"""
配置管理模块 - 负责加载和提供配置信息
"""
import os
import yaml
from dotenv import load_dotenv

from src.security import decrypt_config_secret, encrypt_config_secret, mask_secret

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
        self.CONFIG_PATH = os.path.abspath(config_path)
        self._config_from_yaml = {}
        if os.path.exists(self.CONFIG_PATH):
            with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
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
        self.MODEL_NAME = self._config_from_yaml.get('model_name') or os.getenv('MODEL_NAME') or 'gpt-4o'
        self.EMBEDDING_MODEL_NAME = (
            self._config_from_yaml.get('embedding_model_name')
            or os.getenv('EMBEDDING_MODEL_NAME')
            or 'text-embedding-3-small'
        )
        
        # 报警配置
        self.ALARM_THRESHOLD_SOIL_MOISTURE = float(os.getenv("ALARM_THRESHOLD") or self._get_from_yaml(
            "alarm.soil_moisture_threshold", 25.0))
        alarm_enabled_env = os.getenv("ALARM_ENABLED")
        self.ALARM_ENABLED = (
            alarm_enabled_env.lower() == "true"
            if alarm_enabled_env is not None
            else bool(self._get_from_yaml("alarm.enabled", True))
        )
        
        # 日志配置
        self.LOG_LEVEL = os.getenv("LOG_LEVEL") or self._get_from_yaml("logging.level", "INFO")
        self.LOG_FILE = os.getenv("LOG_FILE") or self._get_from_yaml("logging.file", "irrigation_system.log")
        
        # LLM/OPENAI配置
        self.OPENAI_API_KEY = self._resolve_secret(
            env_key='OPENAI_API_KEY',
            yaml_key='openai_api_key',
            encrypted_yaml_key='openai_api_key_encrypted',
        )
        self.OPENAI_BASE_URL = (
            self._config_from_yaml.get('openai_base_url')
            or os.getenv('OPENAI_BASE_URL')
        )
        self.EMBEDDING_API_KEY = self._resolve_secret(
            env_key='EMBEDDING_API_KEY',
            yaml_key='embedding_api_key',
            encrypted_yaml_key='embedding_api_key_encrypted',
            fallback=self.OPENAI_API_KEY,
        )
        self.KNOWLEDGE_TOP_K = int(
            os.getenv('KNOWLEDGE_TOP_K')
            or self._get_from_yaml('knowledge_base.top_k', 4)
        )
        self.KNOWLEDGE_CHUNK_SIZE = int(
            os.getenv('KNOWLEDGE_CHUNK_SIZE')
            or self._get_from_yaml('knowledge_base.chunk_size', 1200)
        )
        self.KNOWLEDGE_CHUNK_OVERLAP = int(
            os.getenv('KNOWLEDGE_CHUNK_OVERLAP')
            or self._get_from_yaml('knowledge_base.chunk_overlap', 180)
        )
        
        # FastAPI 服务配置
        self.APP_HOST = os.getenv('APP_HOST') or self._get_from_yaml('app.host', '0.0.0.0')
        self.APP_PORT = int(os.getenv('APP_PORT') or self._get_from_yaml('app.port', 7860))
        self.FRONTEND_ORIGINS = self._parse_origins(
            os.getenv('FRONTEND_ORIGINS'),
            self._get_from_yaml('app.frontend_origins', ['http://localhost:3000'])
        )
        
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

    def _resolve_secret(self, *, env_key, yaml_key, encrypted_yaml_key, fallback=None):
        env_value = os.getenv(env_key)
        if env_value:
            return env_value

        encrypted_value = self._config_from_yaml.get(encrypted_yaml_key)
        if encrypted_value:
            return decrypt_config_secret(encrypted_value)

        plain_value = self._config_from_yaml.get(yaml_key)
        if plain_value:
            return plain_value

        return fallback

    def _set_in_yaml(self, path, value):
        """按点路径写入嵌套 YAML 配置。"""
        keys = path.split('.')
        target = self._config_from_yaml
        for key in keys[:-1]:
            if not isinstance(target.get(key), dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

    def _delete_in_yaml(self, path):
        keys = path.split('.')
        target = self._config_from_yaml
        for key in keys[:-1]:
            if not isinstance(target, dict) or key not in target:
                return
            target = target[key]
        if isinstance(target, dict):
            target.pop(keys[-1], None)

    def _serialize_secret_status(self, value):
        masked = mask_secret(value)
        return {
            "configured": bool(masked),
            "masked_value": masked,
        }

    def _write_yaml(self):
        """将当前 YAML 配置持久化回 config.yaml。"""
        with open(self.CONFIG_PATH, 'w', encoding='utf-8') as file:
            yaml.safe_dump(self._config_from_yaml, file, allow_unicode=True, sort_keys=False)

    def get_runtime_settings(self):
        """返回前端设置页需要的结构化配置快照。"""
        return {
            "soil_moisture_threshold": self.IRRIGATION_STRATEGY.get("soil_moisture_threshold", 40.0),
            "default_duration_minutes": self.IRRIGATION_STRATEGY.get("default_duration_minutes", 30),
            "alarm_threshold": self.ALARM_THRESHOLD_SOIL_MOISTURE,
            "alarm_enabled": self.ALARM_ENABLED,
            "model_name": self.MODEL_NAME,
            "embedding_model_name": self.EMBEDDING_MODEL_NAME,
            "openai_base_url": self.OPENAI_BASE_URL,
            "knowledge_top_k": self.KNOWLEDGE_TOP_K,
            "knowledge_chunk_size": self.KNOWLEDGE_CHUNK_SIZE,
            "knowledge_chunk_overlap": self.KNOWLEDGE_CHUNK_OVERLAP,
            "openai_api_key_status": self._serialize_secret_status(self.OPENAI_API_KEY),
            "embedding_api_key_status": self._serialize_secret_status(self.EMBEDDING_API_KEY),
            "sensor_ids": self.SENSOR_IDS,
            "collection_interval_minutes": self.DATA_COLLECTION_INTERVAL_MINUTES,
            "db_type": self.DB_TYPE,
            "config_source": self.CONFIG_PATH,
        }

    def update_runtime_settings(self, updates):
        """将前端结构化设置映射回 config.yaml，并同步刷新运行时配置。"""
        mapping = {
            "soil_moisture_threshold": ("irrigation_strategy.soil_moisture_threshold", float),
            "default_duration_minutes": ("irrigation_strategy.default_duration_minutes", int),
            "alarm_threshold": ("alarm.soil_moisture_threshold", float),
            "alarm_enabled": ("alarm.enabled", bool),
            "collection_interval_minutes": ("sensors.collection_interval_minutes", int),
            "sensor_ids": ("sensors.ids", list),
            "model_name": ("model_name", str),
            "embedding_model_name": ("embedding_model_name", str),
            "openai_base_url": ("openai_base_url", str),
            "knowledge_top_k": ("knowledge_base.top_k", int),
            "knowledge_chunk_size": ("knowledge_base.chunk_size", int),
            "knowledge_chunk_overlap": ("knowledge_base.chunk_overlap", int),
        }

        for key, value in updates.items():
            if key not in mapping or value is None:
                continue
            path, caster = mapping[key]
            normalized = [item for item in value if item] if key == "sensor_ids" else caster(value)
            self._set_in_yaml(path, normalized)

        self._update_secret_in_yaml(
            updates=updates,
            runtime_attr="OPENAI_API_KEY",
            plain_yaml_key="openai_api_key",
            encrypted_yaml_key="openai_api_key_encrypted",
            update_key="openai_api_key",
        )
        self._update_secret_in_yaml(
            updates=updates,
            runtime_attr="EMBEDDING_API_KEY",
            plain_yaml_key="embedding_api_key",
            encrypted_yaml_key="embedding_api_key_encrypted",
            update_key="embedding_api_key",
            fallback_attr="OPENAI_API_KEY",
        )

        self._write_yaml()

        if "soil_moisture_threshold" in updates and updates["soil_moisture_threshold"] is not None:
            self.IRRIGATION_STRATEGY["soil_moisture_threshold"] = float(updates["soil_moisture_threshold"])
        if "default_duration_minutes" in updates and updates["default_duration_minutes"] is not None:
            self.IRRIGATION_STRATEGY["default_duration_minutes"] = int(updates["default_duration_minutes"])
        if "alarm_threshold" in updates and updates["alarm_threshold"] is not None:
            self.ALARM_THRESHOLD_SOIL_MOISTURE = float(updates["alarm_threshold"])
        if "alarm_enabled" in updates and updates["alarm_enabled"] is not None:
            self.ALARM_ENABLED = bool(updates["alarm_enabled"])
        if "collection_interval_minutes" in updates and updates["collection_interval_minutes"] is not None:
            self.DATA_COLLECTION_INTERVAL_MINUTES = int(updates["collection_interval_minutes"])
        if "sensor_ids" in updates and updates["sensor_ids"] is not None:
            self.SENSOR_IDS = [item for item in updates["sensor_ids"] if item]
        if "model_name" in updates and updates["model_name"] is not None:
            self.MODEL_NAME = str(updates["model_name"])
        if "embedding_model_name" in updates and updates["embedding_model_name"] is not None:
            self.EMBEDDING_MODEL_NAME = str(updates["embedding_model_name"])
        if "openai_base_url" in updates:
            self.OPENAI_BASE_URL = str(updates["openai_base_url"] or "").strip() or None
        if "knowledge_top_k" in updates and updates["knowledge_top_k"] is not None:
            self.KNOWLEDGE_TOP_K = int(updates["knowledge_top_k"])
        if "knowledge_chunk_size" in updates and updates["knowledge_chunk_size"] is not None:
            self.KNOWLEDGE_CHUNK_SIZE = int(updates["knowledge_chunk_size"])
        if "knowledge_chunk_overlap" in updates and updates["knowledge_chunk_overlap"] is not None:
            self.KNOWLEDGE_CHUNK_OVERLAP = int(updates["knowledge_chunk_overlap"])

        return self.get_runtime_settings()

    def _update_secret_in_yaml(
        self,
        *,
        updates,
        runtime_attr,
        plain_yaml_key,
        encrypted_yaml_key,
        update_key,
        fallback_attr=None,
    ):
        if update_key not in updates:
            return

        raw_value = updates.get(update_key)
        normalized = str(raw_value or "").strip()
        if not normalized:
            self._delete_in_yaml(plain_yaml_key)
            self._delete_in_yaml(encrypted_yaml_key)
            fallback_value = getattr(self, fallback_attr) if fallback_attr else None
            setattr(self, runtime_attr, fallback_value)
            return

        self._delete_in_yaml(plain_yaml_key)
        self._set_in_yaml(encrypted_yaml_key, encrypt_config_secret(normalized))
        setattr(self, runtime_attr, normalized)
    
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

    def _parse_origins(self, origins, default):
        """将环境变量或配置中的前端域名解析为列表。"""
        if isinstance(origins, str):
            return [origin.strip() for origin in origins.split(',') if origin.strip()]
        if isinstance(origins, list):
            return origins
        return default

# 全局配置实例 - 单例模式
config = Config()
