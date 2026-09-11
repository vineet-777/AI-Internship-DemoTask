"""Unicode, punctuation, and legal-suffix normalization for entity names."""

from __future__ import annotations

import re
import unicodedata

LEGAL_SUFFIXES = frozenset(
    {
        "inc",
        "incorporated",
        "llc",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "co",
        "company",
        "plc",
        "gmbh",
    }
)


def normalize_entity_name(value: str) -> str:
    """Return a deterministic comparison key without changing display names."""
    if not isinstance(value, str):
        raise TypeError("entity name must be a string")
    normalized = unicodedata.normalize("NFKD", value).casefold()
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = normalized.replace("&", " and ")
    normalized = "".join(
        character if character.isalnum() else " " for character in normalized
    )
    words = normalized.split()
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return "".join(words)
