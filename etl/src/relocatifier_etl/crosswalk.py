"""Suburb-name → SAL-code lookup for sources that carry no SAL codes.

ADR-0001 bans joining datasets by name. Several upstream sources (RTA rents,
VG property sales, crime exports) simply have no SAL codes, so this module is
the single sanctioned bridge: an exact-match lookup on normalised
(name, state) built from the SAL table itself. It is deliberately strict —
no fuzzy matching, ambiguous names resolve to nothing, and callers must
report their unmatched counts so coverage loss is visible, never silent.
"""

from __future__ import annotations

import re

import pandas as pd

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def normalise_name(name: str) -> str:
    """Canonical form for matching: uppercase, punctuation/whitespace collapsed.

    "Bli Bli" -> "BLI BLI"; "O'Connell" -> "O CONNELL"; "MT COOT-THA" -> "MT COOT THA".
    """
    return _NON_ALNUM.sub(" ", name.upper()).strip()


class NameLookup:
    """Exact (normalised name, state) -> sal_code; None when unknown or ambiguous."""

    def __init__(self, suburbs: pd.DataFrame):
        """suburbs needs columns: sal_code, name, state."""
        self._map: dict[tuple[str, str], str | None] = {}
        self.ambiguous: set[tuple[str, str]] = set()
        for row in suburbs.itertuples():
            key = (normalise_name(row.name), row.state)
            if key in self._map:
                # Same display name twice within a state — refuse to guess.
                self._map[key] = None
                self.ambiguous.add(key)
            else:
                self._map[key] = row.sal_code

    def sal_code(self, name: str, state: str) -> str | None:
        return self._map.get((normalise_name(name), state.upper()))
