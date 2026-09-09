"""Capture pipeline console output to a log file alongside its results."""

from __future__ import annotations

import atexit
import sys
from contextlib import contextmanager
from pathlib import Path


class _Tee:
    """Write to two streams at once (used to mirror stdout into a log file)."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data: str) -> None:
        for stream in self._streams:
            stream.write(data)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


def start_processing_log(
    output_dir: str | Path,
    filename: str = "processing_log.txt",
) -> None:
    """Mirror console output to ``output_dir/<filename>``.

    The log file is closed and stdout restored automatically when the process exits, so
    a pipeline script only needs this one call - no matching "stop" call is required.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(output_dir / filename, "w", encoding="utf-8")
    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, log_file)

    def _stop() -> None:
        sys.stdout = original_stdout
        log_file.close()

    atexit.register(_stop)


@contextmanager
def processing_log(output_dir: str | Path, filename: str = "processing_log.txt"):
    """Context-manager form of :func:`start_processing_log`."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(output_dir / filename, "w", encoding="utf-8")
    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, log_file)
    try:
        yield
    finally:
        sys.stdout = original_stdout
        log_file.close()
