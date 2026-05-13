"""
数据采集模块 - 负责模拟或从物理传感器收集数据
"""
import time
import datetime
from typing import List, Dict, Any

from src.logger_config import logger
from src.config import config
from src.exceptions.exceptions import InvalidSensorDataError

# 模块级模拟湿度状态：线性下降模拟土壤自然蒸发
_mock_moisture = 90.0
_mock_last_time = time.time()
_DECREASE_RATE = 0.0014  # 90→30 约半天（12h），模拟真实土壤蒸发


def sync_mock_moisture(moisture: float) -> None:
    """由灌溉服务调用，同步灌溉后的湿度值，确保线性增减连贯"""
    global _mock_moisture, _mock_last_time
    _mock_moisture = moisture
    _mock_last_time = time.time()


def _step_mock_moisture() -> float:
    """按时间线性递减湿度，模拟土壤自然蒸发"""
    global _mock_moisture, _mock_last_time
    now = time.time()
    elapsed = now - _mock_last_time
    _mock_last_time = now
    _mock_moisture = max(10.0, _mock_moisture - elapsed * _DECREASE_RATE)
    return _mock_moisture


class DataCollectionModule:
    """
    负责模拟或从物理传感器收集数据
    """
    def __init__(self, sensor_ids: List[str] = None):
        """
        初始化数据采集模块

        :param sensor_ids: 传感器ID列表，如果为None则使用配置中的传感器IDs
        """
        self.sensor_ids = sensor_ids or config.SENSOR_IDS
        logger.info(f"DataCollectionModule initialized for sensors: {self.sensor_ids}")

    def get_data(self) -> Dict[str, Any]:
        """
        模拟或读取传感器的数据

        :return: 包含时间戳、传感器ID和数据的字典
        """
        try:
            sensor_id = self.sensor_ids[0] if self.sensor_ids else config.SENSOR_IDS[0]

            soil_moisture = round(_step_mock_moisture(), 2)
            temperature = 25.0
            light_intensity = 500.0
            rainfall = 0.0

            data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "sensor_id": sensor_id,
                "data": {
                    "soil_moisture": soil_moisture,
                    "temperature": temperature,
                    "light_intensity": light_intensity,
                    "rainfall": rainfall
                }
            }

            logger.debug(f"Collected data from sensor {sensor_id}: {data['data']}")
            return data

        except Exception as e:
            error_msg = f"Error collecting sensor data: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise InvalidSensorDataError(error_msg) from e

    def collect_and_store(self, db=None):
        """
        收集传感器数据并存储到数据库

        :param db: 数据库会话，如果为None则仅返回数据不存储
        :return: 收集的数据
        """
        data = self.get_data()

        if db is not None:
            from src.database.models import SensorData
            timestamp = datetime.datetime.fromisoformat(data["timestamp"])
            sensor_data = SensorData(
                sensor_id=data["sensor_id"],
                timestamp=timestamp,
                soil_moisture=data["data"]["soil_moisture"],
                temperature=data["data"]["temperature"],
                light_intensity=data["data"]["light_intensity"],
                rainfall=data["data"]["rainfall"],
                raw_data=data
            )
            db.add(sensor_data)
            db.commit()
            logger.info(f"Stored sensor data from {data['sensor_id']} to database")

        return data
