"""
Comprehensive Telemetry, High-Resolution Monotonic Timing, and Structured Logging
for Nobeth Universal OCR.
"""

import logging
import re
import sys
import time
import uuid
from typing import Any, Callable, Dict, Optional

# Type alias for decoupled progress callbacks
# Signature: (stage_name: str, progress_ratio: Optional[float], metadata: Optional[Dict[str, Any]])
ProgressCallback = Callable[[str, Optional[float], Optional[Dict[str, Any]]], None]

# Logger Name
LOGGER_NAME = "nobeth_ocr"


def format_duration(seconds: float) -> str:
    """
    Formats a duration in seconds into a human-readable, consistent string.
    - Sub-second durations (< 1.0s) are formatted in milliseconds (e.g. '14 ms', '342 ms').
    - Multi-second durations (< 60.0s) are formatted in seconds with 2 decimal places (e.g. '1.82 s', '12.46 s').
    - Longer durations are formatted as minutes and seconds (e.g. '1m 24.3s').
    """
    if seconds is None or seconds < 0:
        return "0 ms"
    if seconds < 1.0:
        ms = int(round(seconds * 1000))
        return f"{ms} ms"
    if seconds < 60.0:
        return f"{seconds:.2f} s"
    mins = int(seconds // 60)
    rem_secs = seconds % 60
    return f"{mins}m {rem_secs:.1f}s"


def generate_operation_id(prefix: str = "OCR") -> str:
    """
    Generates a short, collision-resistant correlation operation ID.
    Example: 'OCR-7F3A'
    """
    token = uuid.uuid4().hex[:4].upper()
    return f"{prefix}-{token}"


def sanitize_log_message(msg: str) -> str:
    """
    Sanitizes log messages to ensure sensitive data (API keys, authorization headers,
    raw document contents, etc.) are never leaked to logs.
    """
    if not msg:
        return ""
    # Mask potential Gemini API keys (e.g. AQ.xxx, AIzaSy...)
    msg = re.sub(r"AQ\.[A-Za-z0-9_-]{20,}", "[REDACTED_API_KEY]", msg)
    msg = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_API_KEY]", msg)
    msg = re.sub(r"(?i)(api[_-]?key\s*[:=]\s*)['\"]?[A-Za-z0-9_.-]+['\"]?", r"\1[REDACTED]", msg)
    msg = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9_.-]+", r"\1[REDACTED]", msg)
    # Strip long base64 chunks if any
    msg = re.sub(r";base64,[A-Za-z0-9+/=]{40,}", ";base64,[REDACTED_DATA]", msg)
    return msg


class NobethLogFormatter(logging.Formatter):
    """
    Structured, visually aligned log formatter for Nobeth Universal OCR.
    Format: timestamp | level | operation_id | stage | event | message
    Example: 14:21:35.184 | INFO  | OCR-7F3A | VISION OCR             | START   | 1 page
    """

    def format(self, record: logging.LogRecord) -> str:
        # Monotonic time formatted as HH:MM:SS.mmm
        created_sec = record.created
        created_time = time.localtime(created_sec)
        msecs = int(record.msecs)
        time_str = f"{time.strftime('%H:%M:%S', created_time)}.{msecs:03d}"

        level_str = f"{record.levelname:<5}"
        op_id = getattr(record, "op_id", "APP")
        op_str = f"{str(op_id):<8}"
        stage = getattr(record, "stage", "SYSTEM")
        stage_str = f"{str(stage):<24}"
        event = getattr(record, "event", "INFO")
        event_str = f"{str(event):<7}"

        raw_msg = record.getMessage()
        sanitized_msg = sanitize_log_message(raw_msg)

        formatted_line = f"{time_str} | {level_str} | {op_str} | {stage_str} | {event_str} | {sanitized_msg}"

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                clean_exc = sanitize_log_message(record.exc_text)
                formatted_line = f"{formatted_line}\n{clean_exc}"

        return formatted_line


def setup_app_logger(logger_name: str = LOGGER_NAME) -> logging.Logger:
    """
    Configures and returns the application logger.
    Guarantees idempotency: multiple calls (e.g. across Streamlit reruns or launcher
    invocations) will NEVER attach duplicate handlers.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Avoid duplicate printing to root logger

    # Check if a StreamHandler with NobethLogFormatter is already present
    has_custom_handler = any(
        isinstance(h, logging.StreamHandler) and isinstance(h.formatter, NobethLogFormatter)
        for h in logger.handlers
    )

    if not has_custom_handler:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(NobethLogFormatter())
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)

    return logger


def get_app_logger(logger_name: str = LOGGER_NAME) -> logging.Logger:
    """Returns the application logger instance."""
    return logging.getLogger(logger_name)


class OperationTimer:
    """
    High-resolution monotonic timer based on time.perf_counter().
    Measures duration of individual stages and the overall operation reliably.
    """

    def __init__(self, op_id: Optional[str] = None):
        self.op_id = op_id or generate_operation_id()
        self.start_time = time.perf_counter()
        self.end_time: Optional[float] = None
        self.stage_starts: Dict[str, float] = {}
        self.stage_durations: Dict[str, float] = {}

    def start_stage(self, stage_name: str) -> None:
        """Starts timing a specific named stage."""
        self.stage_starts[stage_name] = time.perf_counter()

    def end_stage(self, stage_name: str) -> float:
        """Ends timing a specific stage and returns elapsed duration in seconds."""
        now = time.perf_counter()
        st = self.stage_starts.get(stage_name, self.start_time)
        dur = max(0.0, now - st)
        self.stage_durations[stage_name] = dur
        return dur

    def get_stage_duration(self, stage_name: str) -> Optional[float]:
        """Returns the recorded duration of a stage, if recorded."""
        return self.stage_durations.get(stage_name)

    def elapsed(self) -> float:
        """Returns elapsed time from operation start until now without stopping."""
        now = self.end_time if self.end_time is not None else time.perf_counter()
        return max(0.0, now - self.start_time)

    def stop(self) -> float:
        """Stops the timer and returns total elapsed duration in seconds."""
        if self.end_time is None:
            self.end_time = time.perf_counter()
        return max(0.0, self.end_time - self.start_time)


# Logging Helper Functions
def log_operation_banner(op_id: str, title: str = "DOCUMENT PROCESSING") -> None:
    """Logs the clean, visual start banner for an operation."""
    logger = get_app_logger()
    border = "=" * 70
    banner = (
        f"\n{border}\n"
        f" NOBETH UNIVERSAL OCR | {title.upper()}\n"
        f" Operation: {op_id}\n"
        f"{border}"
    )
    logger.info(banner, extra={"op_id": op_id, "stage": "OPERATION", "event": "START"})


def log_stage_start(op_id: str, stage: str, message: str = "") -> None:
    """Logs a stage start event."""
    logger = get_app_logger()
    logger.info(
        message or "Started",
        extra={"op_id": op_id, "stage": stage.upper(), "event": "START"},
    )


def log_stage_success(op_id: str, stage: str, duration_sec: float, message: str = "") -> None:
    """Logs a stage success event with duration."""
    logger = get_app_logger()
    dur_str = format_duration(duration_sec)
    msg = f"{dur_str} | {message}" if message else dur_str
    logger.info(
        msg,
        extra={"op_id": op_id, "stage": stage.upper(), "event": "SUCCESS"},
    )


def log_stage_failure(op_id: str, stage: str, duration_sec: float, error_msg: str) -> None:
    """Logs a stage failure event with duration and sanitized exception message."""
    logger = get_app_logger()
    dur_str = format_duration(duration_sec)
    sanitized_err = sanitize_log_message(error_msg)
    logger.error(
        f"{dur_str} | FAILED: {sanitized_err}",
        extra={"op_id": op_id, "stage": stage.upper(), "event": "FAILED"},
    )


def log_stage_retry(op_id: str, stage: str, attempt: int, duration_sec: float, reason: str) -> None:
    """Logs a transient retry event."""
    logger = get_app_logger()
    dur_str = format_duration(duration_sec)
    sanitized_reason = sanitize_log_message(reason)
    logger.warning(
        f"Attempt {attempt} failed in {dur_str} ({sanitized_reason}) - retrying...",
        extra={"op_id": op_id, "stage": stage.upper(), "event": "RETRY"},
    )


def log_operation_summary(
    op_id: str,
    success: bool,
    total_duration_sec: float,
    message: str = "",
) -> None:
    """Logs the clean, visual summary at the end of an operation."""
    logger = get_app_logger()
    border = "=" * 70
    status_str = "SUCCESS" if success else "FAILED"
    dur_str = format_duration(total_duration_sec)
    details_part = f" Details: {message}\n" if message else ""
    summary = (
        f"\n{border}\n"
        f" RESULT: {status_str} | Total measured duration: {dur_str}\n"
        f"{details_part}"
        f"{border}\n"
    )
    if success:
        logger.info(summary, extra={"op_id": op_id, "stage": "TOTAL", "event": "SUCCESS"})
    else:
        logger.error(summary, extra={"op_id": op_id, "stage": "TOTAL", "event": "FAILED"})
