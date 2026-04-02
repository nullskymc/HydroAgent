"""
数据采集模块 - 负责模拟或从物理传感器收集数据
"""
import random
import datetime
from typing import List, Dict, Any

from src.logger_config import logger
from src.config import config
from src.exceptions.exceptions import InvalidSensorDataError

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
            # 在实际应用中，这里会与物理传感器交互
            # 目前使用随机数据模拟传感器读数
            sensor_id = random.choice(self.sensor_ids)
            
            # 生成随机但合理的传感器数据
            soil_moisture = round(random.uniform(10, 90), 2)  # 土壤湿度百分比
            temperature = round(random.uniform(5, 35), 2)     # 温度(摄氏度)
            light_intensity = round(random.uniform(100, 900), 2)  # 光照强度(lux)
            rainfall = round(random.uniform(0, 5), 2)         # 降雨量(mm)
            
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
        
        # 如果提供了数据库会话，则存储数据
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
