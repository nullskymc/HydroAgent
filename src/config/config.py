"""
配置管理模块 - 负责加载和提供配置信息
"""
import os
import tempfile
import yaml
from dotenv import load_dotenv

from src.security import mask_secret

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
            "apis.weather_service_url", "https://api.open-meteo.com/v1/forecast")
        
        # 传感器配置
        self.SENSOR_IDS = os.getenv("SENSOR_IDS") and os.getenv("SENSOR_IDS").split(",") or self._get_from_yaml("sensors.ids", ["sensor_001", "sensor_002"])
        self.LEGACY_COLLECTION_INTERVAL_MINUTES = int(self._get_from_yaml("sensors.collection_interval_minutes", 5))
        
        # 灌溉策略（仅作为历史 YAML 回填值，运行期业务配置改由数据库托管）
        self.LEGACY_DEFAULT_SOIL_MOISTURE_THRESHOLD = float(
            self._get_from_yaml("irrigation_strategy.soil_moisture_threshold", 30.0)
        )
        self.LEGACY_DEFAULT_DURATION_MINUTES = int(
            self._get_from_yaml("irrigation_strategy.default_duration_minutes", 30)
        )
        self.IRRIGATION_STRATEGY = {
            "soil_moisture_threshold": self.LEGACY_DEFAULT_SOIL_MOISTURE_THRESHOLD,
            "default_duration_minutes": self.LEGACY_DEFAULT_DURATION_MINUTES,
        }
        
        # 模型配置
        self.MODEL_PATH = os.getenv("MODEL_PATH") or self._get_from_yaml("ml_model.path", None)
        self.MODEL_INPUT_SIZE = int(os.getenv("MODEL_INPUT_SIZE") or self._get_from_yaml("ml_model.input_size", 6))
        self.MODEL_HIDDEN_SIZE = int(os.getenv("MODEL_HIDDEN_SIZE") or self._get_from_yaml("ml_model.hidden_size", 50))
        self.MODEL_NAME = self._config_from_yaml.get('model_name') or 'gpt-4o'
        self.EMBEDDING_MODEL_NAME = (
            self._config_from_yaml.get('embedding_model_name')
            or 'text-embedding-3-small'
        )
        
        # 报警配置（仅作为历史 YAML 回填值，运行期业务配置改由数据库托管）
        self.LEGACY_ALARM_THRESHOLD = float(self._get_from_yaml("alarm.soil_moisture_threshold", 25.0))
        self.LEGACY_ALARM_ENABLED = bool(self._get_from_yaml("alarm.enabled", True))
        self.ALARM_THRESHOLD_SOIL_MOISTURE = self.LEGACY_ALARM_THRESHOLD
        self.ALARM_ENABLED = self.LEGACY_ALARM_ENABLED
        
        # 日志配置
        self.LOG_LEVEL = os.getenv("LOG_LEVEL") or self._get_from_yaml("logging.level", "INFO")
        self.LOG_FILE = os.getenv("LOG_FILE") or self._get_from_yaml("logging.file", "irrigation_system.log")
        
        # LLM/OPENAI配置
        self.OPENAI_API_KEY = self._resolve_secret(
            env_key='OPENAI_API_KEY',
            yaml_key='openai_api_key',
        )
        self.OPENAI_BASE_URL = (
            self._config_from_yaml.get('openai_base_url')
            or "https://api.openai.com/v1"
        )
        self.EMBEDDING_API_KEY = self._resolve_secret(
            env_key='EMBEDDING_API_KEY',
            yaml_key='embedding_api_key',
            fallback=self.OPENAI_API_KEY,
        )
        self.LEGACY_KNOWLEDGE_TOP_K = int(self._get_from_yaml('knowledge_base.top_k', 4))
        self.LEGACY_KNOWLEDGE_CHUNK_SIZE = int(self._get_from_yaml('knowledge_base.chunk_size', 1200))
        self.LEGACY_KNOWLEDGE_CHUNK_OVERLAP = int(self._get_from_yaml('knowledge_base.chunk_overlap', 180))
        self.KNOWLEDGE_TOP_K = self.LEGACY_KNOWLEDGE_TOP_K
        self.KNOWLEDGE_CHUNK_SIZE = self.LEGACY_KNOWLEDGE_CHUNK_SIZE
        self.KNOWLEDGE_CHUNK_OVERLAP = self.LEGACY_KNOWLEDGE_CHUNK_OVERLAP
        self.DATA_COLLECTION_INTERVAL_MINUTES = self.LEGACY_COLLECTION_INTERVAL_MINUTES
        
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
        self.sync_yaml_to_environment()

        # 演示模式：禁止注册新用户，仅保留唯一管理员账号
        self.DEMO_MODE = os.getenv('DEMO_MODE', '').strip().lower() == 'true'
    
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

    def _resolve_secret(self, *, env_key, yaml_key, fallback=None):
        env_value = os.getenv(env_key)
        if env_value:
            return env_value

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
        config_dir = os.path.dirname(self.CONFIG_PATH) or "."
        os.makedirs(config_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=config_dir, delete=False) as file:
            yaml.safe_dump(self._config_from_yaml, file, allow_unicode=True, sort_keys=False)
            temp_path = file.name
        os.replace(temp_path, self.CONFIG_PATH)

    def sync_yaml_to_environment(self):
        """将 YAML 托管的模型/密钥配置同步到进程环境变量，兼容依赖 env 的库。"""
        env_mapping = {
            "OPENAI_API_KEY": self.OPENAI_API_KEY,
            "EMBEDDING_API_KEY": self.EMBEDDING_API_KEY,
            "OPENAI_BASE_URL": self.OPENAI_BASE_URL,
            "MODEL_NAME": self.MODEL_NAME,
            "EMBEDDING_MODEL_NAME": self.EMBEDDING_MODEL_NAME,
        }
        for key, value in env_mapping.items():
            normalized = str(value or "").strip()
            if normalized:
                os.environ[key] = normalized
            else:
                os.environ.pop(key, None)

    def get_yaml_settings(self):
        """返回由 YAML 托管的模型与环境配置快照。"""
        return {
            "model_name": self.MODEL_NAME,
            "embedding_model_name": self.EMBEDDING_MODEL_NAME,
            "openai_base_url": self.OPENAI_BASE_URL,
            "openai_api_key_status": self._serialize_secret_status(self.OPENAI_API_KEY),
            "embedding_api_key_status": self._serialize_secret_status(self.EMBEDDING_API_KEY),
            "db_type": self.DB_TYPE,
            "config_source": self.CONFIG_PATH,
        }

    def get_runtime_settings(self):
        """兼容旧调用；现仅返回 YAML 托管字段。"""
        return self.get_yaml_settings()

    def update_yaml_settings(self, updates):
        """将前端结构化设置映射回 config.yaml，并同步刷新运行时配置。"""
        mapping = {
            "model_name": ("model_name", str),
            "embedding_model_name": ("embedding_model_name", str),
            "openai_base_url": ("openai_base_url", str),
        }

        for key, value in updates.items():
            if key not in mapping or value is None:
                continue
            path, caster = mapping[key]
            self._set_in_yaml(path, caster(value))

        self._update_secret_in_yaml(
            updates=updates,
            runtime_attr="OPENAI_API_KEY",
            plain_yaml_key="openai_api_key",
            update_key="openai_api_key",
        )
        self._update_secret_in_yaml(
            updates=updates,
            runtime_attr="EMBEDDING_API_KEY",
            plain_yaml_key="embedding_api_key",
            update_key="embedding_api_key",
            fallback_attr="OPENAI_API_KEY",
        )

        self._write_yaml()
        if "model_name" in updates and updates["model_name"] is not None:
            self.MODEL_NAME = str(updates["model_name"])
        if "embedding_model_name" in updates and updates["embedding_model_name"] is not None:
            self.EMBEDDING_MODEL_NAME = str(updates["embedding_model_name"])
        if "openai_base_url" in updates:
            self.OPENAI_BASE_URL = str(updates["openai_base_url"] or "").strip() or None
        self.sync_yaml_to_environment()

        return self.get_yaml_settings()

    def update_runtime_settings(self, updates):
        """兼容旧调用；现仅更新 YAML 托管字段。"""
        return self.update_yaml_settings(updates)

    def _update_secret_in_yaml(
        self,
        *,
        updates,
        runtime_attr,
        plain_yaml_key,
        update_key,
        fallback_attr=None,
    ):
        if update_key not in updates:
            return

        raw_value = updates.get(update_key)
        normalized = str(raw_value or "").strip()
        if not normalized:
            self._delete_in_yaml(plain_yaml_key)
            fallback_value = getattr(self, fallback_attr) if fallback_attr else None
            setattr(self, runtime_attr, fallback_value)
            return

        self._set_in_yaml(plain_yaml_key, normalized)
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
