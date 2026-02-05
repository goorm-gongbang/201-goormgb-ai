"""Structured Logger for Defense PoC-0 Audit Trail.

Provides file-based JSONL logging for decision audit trail.
All DecisionLogEntry objects are written as-is with no filtering or transformation.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .schema import DecisionLogEntry


class DecisionLogger:
    """File-based structured logger for decision audit trail.

    Writes DecisionLogEntry objects to a JSONL file (1 line = 1 entry).
    Designed to be fail-safe: logging failures do not interrupt defense logic.

    Instance Management:
        We use a module-level factory function (get_default_logger) instead of
        a strict Singleton pattern. This provides:
        - Easy reuse from Runner without global state
        - Flexibility to create multiple loggers if needed (e.g., testing)
        - Simpler implementation without metaclass complexity
    """

    def __init__(
        self,
        log_dir: str = "logs",
        filename: str = "decision_audit.jsonl",
    ) -> None:
        """Initialize the logger.

        Args:
            log_dir: Directory to store log files.
            filename: Name of the log file.
        """
        self._log_dir = Path(log_dir)
        self._filename = filename
        self._file_path = self._log_dir / self._filename
        self._file: Optional[object] = None
        self._is_setup = False

    @property
    def file_path(self) -> Path:
        """Return the full path to the log file."""
        return self._file_path

    def setup(self) -> None:
        """Initialize the logger and prepare the log file.

        Creates the log directory if it doesn't exist.

        File Handling Strategy:
            We TRUNCATE (clear) the existing file on setup.
            This is chosen over backup for PoC-0 simplicity:
            - Each scenario run starts fresh
            - No accumulation of old logs
            - Easier debugging/testing
            For production, consider backup or rotation.
        """
        try:
            # Create directory if needed
            self._log_dir.mkdir(parents=True, exist_ok=True)

            # Open file in write mode (truncate existing)
            # Using 'w' mode intentionally clears the file
            self._file = open(
                self._file_path,
                mode="w",
                encoding="utf-8",
            )
            self._is_setup = True

        except OSError as e:
            print(f"[DecisionLogger] setup failed: {e}")
            self._is_setup = False

    def log(self, entry: DecisionLogEntry) -> None:
        """Write a decision log entry to the file.

        Args:
            entry: The DecisionLogEntry to log.

        Note:
            Fail-safe: Errors are caught and printed, never raised.
            Logging failures must not interrupt defense logic.
        """
        if not self._is_setup or self._file is None:
            print("[DecisionLogger] log called before setup, skipping")
            return

        try:
            # Convert to JSON and write as single line (JSONL format)
            json_line = entry.to_json()
            self._file.write(json_line + "\n")
            self._file.flush()  # Ensure immediate write for debugging

        except (OSError, TypeError, ValueError) as e:
            print(f"[DecisionLogger] write failed: {e}")

    def close(self) -> None:
        """Close the log file and release resources.

        Safe to call multiple times.
        """
        if self._file is not None:
            try:
                self._file.close()
            except OSError as e:
                print(f"[DecisionLogger] close failed: {e}")
            finally:
                self._file = None
                self._is_setup = False

    def __enter__(self) -> "DecisionLogger":
        """Context manager entry."""
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


# =============================================================================
# Module-level Default Instance
# =============================================================================

# Default logger instance for easy reuse
# Using factory function pattern for flexibility
_default_logger: Optional[DecisionLogger] = None


def get_default_logger(
    log_dir: str = "logs",
    filename: str = "decision_audit.jsonl",
    force_new: bool = False,
) -> DecisionLogger:
    """Get or create the default DecisionLogger instance.

    This factory function provides easy reuse while maintaining flexibility:
    - First call creates the instance
    - Subsequent calls return the same instance
    - force_new=True creates a fresh instance

    Args:
        log_dir: Directory for log files.
        filename: Log filename.
        force_new: If True, close existing and create new instance.

    Returns:
        DecisionLogger instance.
    """
    global _default_logger

    if force_new and _default_logger is not None:
        _default_logger.close()
        _default_logger = None

    if _default_logger is None:
        _default_logger = DecisionLogger(log_dir=log_dir, filename=filename)

    return _default_logger


def reset_default_logger() -> None:
    """Close and reset the default logger instance.

    Useful for testing or when switching log files.
    """
    global _default_logger

    if _default_logger is not None:
        _default_logger.close()
        _default_logger = None


__all__ = [
    "DecisionLogger",
    "get_default_logger",
    "reset_default_logger",
]
