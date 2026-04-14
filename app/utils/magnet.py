from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, unquote, urlparse


BTIH_RE = re.compile(r"btih:([A-Fa-f0-9]{40}|[A-Z2-7]{32})")


def extract_magnet_hash(magnet_uri: str) -> str | None:
    match = BTIH_RE.search(magnet_uri)
    if not match:
        return None
    return match.group(1).lower()


def magnet_display_name(magnet_uri: str) -> str | None:
    parsed = urlparse(magnet_uri)
    params = parse_qs(parsed.query)
    dn = params.get("dn")
    if dn:
        return unquote(dn[0])
    return None


def stable_remote_file_id(remote_path: str) -> str:
    return hashlib.sha1(remote_path.encode("utf-8")).hexdigest()
