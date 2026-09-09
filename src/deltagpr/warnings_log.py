"""Collects warnings raised during a pipeline run so they can be repeated at the end.

Line-by-line processing prints a lot of output; collecting warnings here lets a
pipeline script print a short, unmissable summary after everything else is done.
"""

from __future__ import annotations

_warnings: list[str] = []


def log_warning(message: str) -> None:
    """Print a warning immediately and record it for the end-of-run summary."""
    print(f"  Warning: {message}")
    _warnings.append(message)


def print_warnings_summary() -> None:
    """Print all distinct warnings collected so far."""
    unique_messages = list(dict.fromkeys(_warnings))
    if not unique_messages:
        return
    print()
    print(f"WARNING SUMMARY ({len(unique_messages)} issue(s)):")
    for message in unique_messages:
        print(f"  - {message}")
