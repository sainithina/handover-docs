"""ID generation utilities."""

import hashlib


def short_hash(text: str, n: int = 12) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return digest[:n]


def make_id(prefix: str, stable_text: str) -> str:
    return f"{prefix}_{short_hash(stable_text)}"
