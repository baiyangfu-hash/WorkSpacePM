"""统一日志工厂"""

import logging
import sys


def setup_logger(
    *, app_name: str, log_level: str, bind_to: logging.Logger | None = None
) -> logging.Logger:
    """配置并返回一个 logger 实例。

    Parameters
    ----------
    app_name : str
        应用名称，用作 logger 名称。
    log_level : str
        日志级别字符串（如 'DEBUG', 'INFO'）。
    bind_to : Optional[logging.Logger]
        可选，将配置绑定到已有 logger。

    Returns
    -------
    logging.Logger
        配置好的 logger 实例。
    """
    logger = logging.getLogger(app_name)
    normalised_log_level = getattr(logging, log_level.upper()) or logging.INFO
    logger.setLevel(normalised_log_level)

    # 幂等：已配置 handler 则不再重复添加，仅更新级别
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(asctime)s [%(levelname)8.8s] %(message)s")
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if bind_to:
        bind_to.handlers = logger.handlers
        bind_to.setLevel(log_level)

    return logger
