"""Pure decision logic for deciding whether a Full ETL batch is needed."""

from __future__ import annotations

from typing import Mapping


def should_process_batch(
    *,
    wordlist_changed: bool,
    extraction_states: list[Mapping[str, object]],
    production_exists: bool,
    force: bool = False,
) -> bool:
    """Return whether downstream transform/stage/publish work is required.

    A first run must publish even when the source inventory is unchanged because
    the database may be empty.  Subsequent runs can safely finish without
    touching production when neither the wordlist nor any source changed.
    """

    if force or wordlist_changed or not production_exists:
        return True
    return any(int(state.get("changed_source_count", 0) or 0) > 0 for state in extraction_states)


__all__ = ["should_process_batch"]
