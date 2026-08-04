"""Pure configuration gates for production publishing."""

from __future__ import annotations

import os


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def publish_enabled(value: str | None = None) -> bool:
    """Return whether a batch is allowed to replace production tables.

    Publishing is deliberately opt-in.  Passing ``None`` reads the
    ``HSK_PUBLISH_ENABLED`` environment variable; an unset or unrecognised
    value is treated as disabled so a misconfigured deployment cannot write
    production by accident.
    """

    raw = os.getenv("HSK_PUBLISH_ENABLED", "false") if value is None else value
    return str(raw).strip().lower() in TRUE_VALUES


__all__ = ["publish_enabled"]
