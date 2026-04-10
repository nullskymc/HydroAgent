"""
控制执行模块 - 负责与灌溉硬件（或模拟）交互
"""
import datetime
from typing import Dict, Any, Optional

from src.database.models import SessionLocal
from src.logger_config import logger
from src.exceptions.exceptions import IrrigationDeviceError
from src.services.system_settings_service import get_default_duration_minutes

class ControlExecutionModule:
    """
    负责与灌溉硬件（或模拟）交互
    """
    def __init__(self):
        """初始化控制执行模块"""
        # 模拟设备状态: 'stopped', 'running', 'error'
        self._device_status = "stopped"
        self.last_start_time = None
        self.duration_minutes = 0
        logger.info("ControlExecutionModule initialized.")
    
    def start_irrigation(self, duration_minutes: int = None) -> Dict[str, Any]:
        """
        启动灌溉设备
        
        :param duration_minutes: 灌溉时长（分钟），如果为None则使用配置中的默认时长
        :return: 执行结果字典
        :raises: IrrigationDeviceError 如果设备控制失败
        """
        if duration_minutes is None:
            duration_minutes = _load_default_duration_minutes()
        
        if self._device_status == "running":
            message = "灌溉已经在运行中。"
            logger.warning(message)
            return {"status": "warning", "message": message}
        
        try:
            logger.info(f"启动灌溉，持续{duration_minutes}分钟。")
            # === 在此与硬件交互 ===
            # 模拟硬件操作
            self._device_status = "running"
            self.last_start_time = datetime.datetime.now()
            self.duration_minutes = duration_minutes
            # === 硬件交互结束 ===
            
            message = f"灌溉成功启动，将持续{duration_minutes}分钟。"
            logger.info(message)
            self._log_irrigation_event("start", duration_minutes * 60)  # 记录日志
            return {"status": "success", "message": message, "device_status": self._device_status}
            
        except Exception as e:
            self._device_status = "error"  # 更新状态为错误
            error_msg = f"启动灌溉设备失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._log_irrigation_event("start_failed")
            raise IrrigationDeviceError(error_msg) from e
    
    def stop_irrigation(self) -> Dict[str, Any]:
        """
        停止灌溉设备
        
        :return: 执行结果字典
        :raises: IrrigationDeviceError 如果设备控制失败
        """
        if self._device_status == "stopped":
            message = "灌溉已经停止。"
            logger.warning(message)
            return {"status": "warning", "message": message}
        
        try:
            logger.info("停止灌溉。")
            # === 在此与硬件交互 ===
            # 模拟硬件操作
            previous_status = self._device_status
            self._device_status = "stopped"
            # === 硬件交互结束 ===
            
            message = "灌溉已成功停止。"
            logger.info(message)
            if previous_status == "running":  # 只有在运行时停止才记录完成
                self._log_irrigation_event("stop")
            return {"status": "success", "message": message, "device_status": self._device_status}
            
        except Exception as e:
            self._device_status = "error"
            error_msg = f"停止灌溉设备失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._log_irrigation_event("stop_failed")
            raise IrrigationDeviceError(error_msg) from e
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取当前灌溉设备的状态
        
        :return: 包含设备状态和其他信息的字典
        """
        status_info = {
            "device_status": self._device_status,
        }
        
        # 如果正在运行，添加运行信息
        if self._device_status == "running" and self.last_start_time:
            now = datetime.datetime.now()
            elapsed = (now - self.last_start_time).total_seconds() / 60  # 转换为分钟
            remaining = max(0, self.duration_minutes - elapsed)
            
            status_info.update({
                "started_at": self.last_start_time.isoformat(),
                "elapsed_minutes": round(elapsed, 1),
                "remaining_minutes": round(remaining, 1),
                "duration_minutes": self.duration_minutes
            })
        
        logger.debug(f"当前设备状态: {status_info}")
        return status_info
    
    def _log_irrigation_event(self, event_type: str, duration_seconds: int = None):
        """
        (内部方法) 记录灌溉事件到数据库
        
        :param event_type: 事件类型 (start, stop, start_failed, stop_failed)
        :param duration_seconds: 计划的灌溉持续时间（秒）
        """
        now = datetime.datetime.now()
        log_entry = {
            "timestamp": now,
            "event": event_type,
            "status": "logged",  # 简化状态
        }
        
        if event_type == "start":
            log_entry["duration_planned_seconds"] = duration_seconds
            log_entry["start_time"] = self.last_start_time
            
        elif event_type == "stop" and self.last_start_time:
            log_entry["start_time"] = self.last_start_time
            log_entry["end_time"] = now
            log_entry["duration_actual_seconds"] = (now - self.last_start_time).total_seconds()
            log_entry["status"] = "completed"
            self.last_start_time = None  # 重置开始时间
            
        elif "failed" in event_type:
            log_entry["status"] = "failed"
        
        logger.info(f"Logging irrigation event: {log_entry}")
        # 在实际应用中，这里会将log_entry写入数据库IrrigationLog表
        try:
            # 连接数据库并存储日志
            # 使用models.py中的方法
            # db = next(get_db())
            # db_log = IrrigationLog(**log_entry)
            # db.add(db_log)
            # db.commit()
            # logger.debug(f"已将灌溉事件存储到数据库，ID: {db_log.id}")
            pass
        except Exception as e:
            logger.error(f"存储灌溉日志到数据库失败: {str(e)}", exc_info=True)


def _load_default_duration_minutes() -> int:
    db = SessionLocal()
    try:
        return get_default_duration_minutes(db)
    finally:
        db.close()
