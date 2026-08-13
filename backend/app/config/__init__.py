"""配置包"""
from .settings import (
    Config,
    DevelopmentConfig,
    ProductionConfig,
    get_config,
)

__all__ = ['Config', 'DevelopmentConfig', 'ProductionConfig', 'get_config']
