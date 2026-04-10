"""
报警模块 - 负责基于规则（如低湿度）生成和发送警报
"""
from typing import Optional

from src.database.models import SessionLocal
from src.logger_config import logger
from src.services.system_settings_service import get_alarm_settings

class AlarmModule:
    """
    负责基于规则（如低湿度）生成和发送警报
    """
    def __init__(self, alarm_threshold: float = None, enabled: bool = None):
        """
        初始化报警模块
        
        :param alarm_threshold: 触发报警的土壤湿度阈值，默认使用配置
        :param enabled: 是否启用报警功能，默认使用配置
        """
        threshold, alarm_enabled = _load_alarm_defaults()
        self.alarm_threshold = alarm_threshold if alarm_threshold is not None else threshold
        self.enabled = enabled if enabled is not None else alarm_enabled
        logger.info(f"AlarmModule initialized. Threshold: {self.alarm_threshold}%, Enabled: {self.enabled}")
    
    def check_humidity(self, soil_moisture: float) -> bool:
        """
        检查土壤湿度是否低于报警阈值
        
        :param soil_moisture: 当前土壤湿度
        :return: True如果低于阈值，否则False
        """
        return soil_moisture < self.alarm_threshold
    
    def send_alarm(self, message: str):
        """
        发送报警信息（当前实现为日志记录）
        
        :param message: 报警内容
        """
        if not self.enabled:
            logger.info("Alarm sending skipped because alarms are disabled.")
            return
        
        logger.critical(f"ALARM TRIGGERED: {message}")  # 使用CRITICAL级别引起注意
        
        # 在实际应用中，这里可以集成邮件、短信、推送通知等服务
        # self._send_email("admin@example.com", "Irrigation System Alert", message)
        # self._send_sms("+1234567890", message)
    
    def handle_alarm(self, soil_moisture: float) -> Optional[str]:
        """
        处理报警逻辑：检查湿度，如果需要则生成并发送报警
        
        :param soil_moisture: 当前土壤湿度
        :return: 如果触发报警，返回报警信息字符串，否则返回None
        """
        if self.enabled and self.check_humidity(soil_moisture):
            message = f"低土壤湿度警报！当前湿度: {soil_moisture}%, 阈值: {self.alarm_threshold}%"
            self.send_alarm(message)
            return message
        elif self.enabled:
            logger.debug(f"土壤湿度 {soil_moisture}% 高于报警阈值 {self.alarm_threshold}%。无需报警。")
        return None
    
    def enable_alarm(self):
        """启用报警功能"""
        logger.info("启用报警系统。")
        self.enabled = True
    
    def disable_alarm(self):
        """禁用报警功能"""
        logger.info("禁用报警系统。")
        self.enabled = False
    
    def set_threshold(self, threshold: float):
        """
        设置报警阈值
        
        :param threshold: 新的报警阈值
        """
        if threshold < 0 or threshold > 100:
            logger.warning(f"无效的报警阈值: {threshold}%，阈值应该在0-100之间。")
            return
        
        logger.info(f"报警阈值从 {self.alarm_threshold}% 更改为 {threshold}%")
        self.alarm_threshold = threshold
    
    def _send_email(self, recipient: str, subject: str, body: str):
        """
        发送电子邮件报警（示例方法，未实现）
        
        :param recipient: 收件人邮箱
        :param subject: 邮件主题
        :param body: 邮件内容
        """
        logger.info(f"模拟发送邮件到 {recipient}: {subject}")
        # 实际应用中可以使用smtplib或第三方服务如SendGrid
    
    def _send_sms(self, phone_number: str, message: str):
        """
        发送短信报警（示例方法，未实现）
        
        :param phone_number: 接收短信的电话号码
        :param message: 短信内容
        """
        logger.info(f"模拟发送短信到 {phone_number}")
        # 实际应用中可以使用Twilio或其他短信API服务


def _load_alarm_defaults() -> tuple[float, bool]:
    db = SessionLocal()
    try:
        return get_alarm_settings(db)
    finally:
        db.close()
