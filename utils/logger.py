"""
Logger module for recording system quality events, defect preventions,
and search performance metrics for Fact-Based Decision Making.
"""
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data"
)
LOG_FILE = os.path.join(LOG_DIR, "app_quality.log")


class AppLogger:
    """Logs System quality events, Poka-Yoke error preventions, and search execution metrics."""

    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path or LOG_FILE
        self._ensure_log_dir()
        self._setup_logger()

    def _ensure_log_dir(self) -> None:
        log_dir = os.path.dirname(self.log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    def _setup_logger(self) -> None:
        self.logger = logging.getLogger("PharmacySystem")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_path, encoding="utf-8")
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [APP-%(category)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def log_event(self, category: str, message: str, level: str = "INFO") -> None:
        """Logs a quality event under specified log category (e.g. SEARCH, POKA_YOKE, AUTH, ERROR)."""
        extra = {"category": category.upper()}
        if level.upper() == "WARNING":
            self.logger.warning(message, extra=extra)
        elif level.upper() == "ERROR":
            self.logger.error(message, extra=extra)
        else:
            self.logger.info(message, extra=extra)

    def log_search_query(self, query_params: dict, execution_time_ms: float, results_count: int) -> None:
        """Logs search query execution parameters and performance metrics for Q13 analysis."""
        msg = f"Query: {query_params} | Time: {execution_time_ms:.3f} ms | Returned: {results_count} rows"
        self.log_event("SEARCH_PERFORMANCE", msg)

    def log_poka_yoke(self, action: str, details: str) -> None:
        """Logs a Poka-Yoke error prevention event (e.g. blocked expired medicine sale)."""
        msg = f"Action: {action} | Prevented: {details}"
        self.log_event("POKA_YOKE", msg, level="WARNING")


_logger_instance: Optional[AppLogger] = None


def get_app_logger() -> AppLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = AppLogger()
    return _logger_instance
