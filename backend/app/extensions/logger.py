"""
统一日志配置(Sprint 0 Release Check - P5)

职责:
- 配置 Python logging,输出到 logs/app.log(按日轮转)
- 控制台同步输出(开发期便于观察)
- 提供统一 logger 句柄,供业务层使用

使用约定:
- from app.extensions.logger import logger
- logger.info("...") / logger.exception("...") 等

不修改业务逻辑;业务层原有的 print 仅在关键异常点替换为 logger。
"""
import os
import logging
from logging.handlers import RotatingFileHandler

# 默认日志格式
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def _resolve_log_dir(app=None):
    """解析日志目录:优先用 app.config['LOG_DIR'],否则 backend/logs"""
    if app and app.config.get('LOG_DIR'):
        return app.config['LOG_DIR']
    # backend/logs(extensions/logger.py 上上上级 = backend)
    here = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(os.path.dirname(here))
    return os.path.join(backend_dir, 'logs')


def setup_logging(app=None):
    """
    初始化全局日志配置。
    在 create_app() 中调用,确保 logs/ 目录存在并配置 root logger。

    :param app: Flask app(用于读取 LOG_DIR / LOG_LEVEL 配置)
    """
    log_dir = _resolve_log_dir(app)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'app.log')

    level_name = (app.config.get('LOG_LEVEL', 'INFO') if app else 'INFO').upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复添加 handler(测试/多次 create_app 场景)
    if any(getattr(h, '_app_handler', False) for h in root.handlers):
        return

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # 文件 handler:按 5MB 轮转,保留 5 个备份
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler._app_handler = True  # 标记,避免重复
    root.addHandler(file_handler)

    # 控制台 handler(开发期观察)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler._app_handler = True
    root.addHandler(console_handler)


# 业务层统一使用的 logger 句柄
logger = logging.getLogger('app')
