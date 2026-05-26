import logging
import sys
from logging.handlers import RotatingFileHandler
from config.settings import LOG_DIR, LOG_LEVEL

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(LOG_LEVEL)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(sh)

    fh = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(fh)

    logger.propagate = False
    return logger
