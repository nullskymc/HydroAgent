"""
日志配置模块 - 配置全局日志记录器
"""
import logging
import os
from src.config import config

def setup_logger():
    """
    配置根日志记录器，所有子 logger 通过传播自动继承 handler。
    """
    # 确保日志文件目录存在
    log_path = os.path.dirname(config.LOG_FILE)
    if log_path and not os.path.exists(log_path):
        os.makedirs(log_path)

    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)

    # 避免重复添加
    if root.handlers:
        root.handlers.clear()

    file_handler = logging.FileHandler(config.LOG_FILE)
    file_handler.setFormatter(log_format)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    root.addHandler(console_handler)

    return root

# 全局日志记录器实例（根 logger）
logger = setup_logger()