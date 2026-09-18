"""日志初始化：统一格式与级别。"""

import logging
import sys

_LOGGING_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_LOGGING_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """配置根日志：输出到 stdout，格式统一。启动时调用一次即可。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOGGING_FORMAT, datefmt=_LOGGING_DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加 handler（如 uvicorn --reload 重载时）
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
