"""
core/logging_config.py — Structured JSON Logging for APRS V6 Pro.

Provides consistent JSON-formatted logging across all modules.
Compatible with log aggregation systems (ELK, Datadog, etc.).
"""
import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import uuid


class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""
    
    def __init__(self, service_name: str = "aprs", include_traceback: bool = True):
        super().__init__()
        self.service_name = service_name
        self.include_traceback = include_traceback
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "service": self.service_name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add trace ID if available
        if hasattr(record, "trace_id"):
            log_data["trace_id"] = record.trace_id
        
        # Add extra fields from record
        extra_fields = {
            k: v for k, v in record.__dict__.items()
            if k not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "name", "pathname", "process", "processName",
                "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info", "trace_id"
            }
        }
        if extra_fields:
            log_data["extra"] = extra_fields
        
        # Add exception info
        if record.exc_info and self.include_traceback:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }
        
        return json.dumps(log_data, default=str, ensure_ascii=False)


class ContextFilter(logging.Filter):
    """Add context (trace_id, user_id, etc.) to log records."""
    
    def __init__(self):
        super().__init__()
        self.context: Dict[str, Any] = {}
    
    def set_context(self, **kwargs):
        self.context.update(kwargs)
    
    def clear_context(self):
        self.context.clear()
    
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self.context.items():
            setattr(record, key, value)
        return True


# Global context filter instance
context_filter = ContextFilter()


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_file: Optional[Path] = None,
    service_name: str = "aprs",
) -> logging.Logger:
    """
    Configure structured logging for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: Use JSON formatting (True) or human-readable (False)
        log_file: Optional file path for file logging
        service_name: Service name for log identification
    
    Returns:
        Configured root logger
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if json_format:
        console_handler.setFormatter(JsonFormatter(service_name=service_name))
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
    console_handler.addFilter(context_filter)
    root_logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        if json_format:
            file_handler.setFormatter(JsonFormatter(service_name=service_name))
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
            )
        file_handler.addFilter(context_filter)
        root_logger.addHandler(file_handler)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with context filter applied."""
    logger = logging.getLogger(name)
    if context_filter not in logger.filters:
        logger.addFilter(context_filter)
    return logger


class LogContext:
    """Context manager for adding structured context to logs."""
    
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.old_context = context_filter.context.copy()
    
    def __enter__(self):
        context_filter.set_context(**self.kwargs)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        context_filter.context.clear()
        context_filter.context.update(self.old_context)


def log_with_context(logger: logging.Logger, level: int, message: str, **kwargs):
    """Log a message with additional structured context."""
    extra = {"extra": kwargs} if kwargs else {}
    logger.log(level, message, extra=extra)


# Convenience functions for common log patterns
def log_gate_start(logger: logging.Logger, gate: int, product_id: str, **kwargs):
    log_with_context(logger, logging.INFO, f"Gate {gate} started", 
                    gate=gate, product_id=product_id, event="gate_start", **kwargs)


def log_gate_result(logger: logging.Logger, gate: int, product_id: str, passed: bool, **kwargs):
    log_with_context(logger, logging.INFO if passed else logging.WARNING,
                    f"Gate {gate} {'PASSED' if passed else 'FAILED'}",
                    gate=gate, product_id=product_id, passed=passed, event="gate_result", **kwargs)


def log_pipeline_result(logger: logging.Logger, product_id: str, verdict: str, score: float, **kwargs):
    log_with_context(logger, logging.INFO, f"Pipeline completed: {verdict}",
                    product_id=product_id, verdict=verdict, score=score, event="pipeline_result", **kwargs)


def log_scrape_result(logger: logging.Logger, marketplace: str, query: str, count: int, **kwargs):
    log_with_context(logger, logging.INFO, f"Scraped {count} products",
                    marketplace=marketplace, query=query, count=count, event="scrape_result", **kwargs)


def log_economics_result(logger: logging.Logger, product_id: str, scenario: str, 
                         net_margin: float, passed: bool, **kwargs):
    log_with_context(logger, logging.INFO if passed else logging.WARNING,
                    f"Economics {scenario}: {net_margin:.1f}% {'PASS' if passed else 'FAIL'}",
                    product_id=product_id, scenario=scenario, net_margin=net_margin, passed=passed,
                    event="economics_result", **kwargs)


if __name__ == "__main__":
    # Demo
    setup_logging(level="DEBUG", json_format=True)
    logger = get_logger("demo")
    
    # Basic logging
    logger.info("Application started", extra={"version": "6.0"})
    
    # With context
    with LogContext(trace_id=str(uuid.uuid4()), user_id="user123", request_id="req456"):
        logger.info("Processing request")
        
        with LogContext(gate=1, product_id="PROD001"):
            log_gate_start(logger, 1, "PROD001")
            log_gate_result(logger, 1, "PROD001", True, bsr=15000, cv=0.05)
        
        log_pipeline_result(logger, "PROD001", "PROCEED", 85.5)
    
    # Error logging
    try:
        raise ValueError("Test error")
    except Exception:
        logger.exception("Error occurred")