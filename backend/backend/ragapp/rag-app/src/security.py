"""Server-side authentication, per-user quotas, and tenant collection names.

Callers are identified only by an API token configured on the server.
Tenant ids never come from the request body.
"""

import hashlib
import hmac
import json
import os
import re
import threading
import time

MIN_TOKEN_LENGTH = 16
DEFAULT_ORIGIN = "http://localhost:3000"
_COLLECTION_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,254}")


def _int_env(name, default, minimum=0, maximum=1_000_000):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < minimum:
        return minimum
    return min(value, maximum)


def _parse_origins(raw):
    """Return explicit http(s) origins. A wildcard is never accepted."""
    if raw is None or raw.strip() == "" or raw.strip() == "*":
        return [DEFAULT_ORIGIN]

    origins = []
    for part in raw.split(","):
        origin = part.strip().rstrip("/")
        if not origin or origin == "*" or origin.lower() == "null":
            continue
        if origin.startswith("http://") or origin.startswith("https://"):
            origins.append(origin)
    return origins or [DEFAULT_ORIGIN]


def _identity_from_mapping(entry):
    if not isinstance(entry, dict):
        return None
    token = entry.get("token")
    user_id = entry.get("user_id")
    tenant_id = entry.get("tenant_id")
    if not all(isinstance(value, str) for value in (token, user_id, tenant_id)):
        return None
    token = token.strip()
    user_id = user_id.strip()
    tenant_id = tenant_id.strip()
    if (
        len(token) < MIN_TOKEN_LENGTH
        or len(token) > 512
        or not user_id
        or not tenant_id
        or len(user_id) > 128
        or len(tenant_id) > 128
    ):
        return None
    return token, {"user_id": user_id, "tenant_id": tenant_id}


def parse_api_tokens(raw):
    """Parse RING_API_TOKENS into token -> {user_id, tenant_id}.

    JSON list:
      [{"token": "...", "user_id": "alice", "tenant_id": "acme"}]

    Simple form, tokens without colons or commas:
      token:user_id:tenant_id,token2:user_id2:tenant_id2
    """
    identities = {}
    if raw is None or raw.strip() == "":
        return identities

    entries = []
    stripped = raw.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return identities
        if isinstance(parsed, dict):
            parsed = [parsed]
        if isinstance(parsed, list):
            entries = parsed
    else:
        for part in stripped.split(","):
            pieces = part.split(":")
            if len(pieces) != 3:
                continue
            entries.append(
                {"token": pieces[0], "user_id": pieces[1], "tenant_id": pieces[2]}
            )

    for entry in entries:
        parsed = _identity_from_mapping(entry)
        if parsed is None:
            continue
        token, identity = parsed
        # First valid definition wins so a duplicate cannot silently replace it.
        identities.setdefault(token, identity)
    return identities


class Settings:
    def __init__(self):
        self.identities = {}
        self.origins = [DEFAULT_ORIGIN]
        self.query_quota = 30
        self.upload_quota = 10
        self.quota_window_seconds = 3600
        self.max_upload_bytes = 20 * 1024 * 1024
        self.max_files_per_request = 20
        self.max_document_chars = 50_000
        self.max_chunks_per_file = 40

    def load(self):
        self.identities = parse_api_tokens(os.environ.get("RING_API_TOKENS", ""))
        self.origins = _parse_origins(os.environ.get("FRONTEND_ORIGIN"))
        self.query_quota = _int_env("QUERY_QUOTA", 30)
        self.upload_quota = _int_env("UPLOAD_QUOTA", 10)
        self.quota_window_seconds = _int_env("QUOTA_WINDOW_SECONDS", 3600, minimum=1)
        self.max_upload_bytes = _int_env(
            "MAX_UPLOAD_BYTES", 20 * 1024 * 1024, minimum=1, maximum=100 * 1024 * 1024
        )
        self.max_files_per_request = _int_env("MAX_FILES_PER_REQUEST", 20, minimum=1, maximum=100)
        self.max_document_chars = _int_env(
            "MAX_DOCUMENT_CHARS", 50_000, minimum=1, maximum=200_000
        )
        self.max_chunks_per_file = _int_env("MAX_CHUNKS_PER_FILE", 40, minimum=1, maximum=200)


settings = Settings()


class QuotaTracker:
    """Fixed-window counter keyed by user id and action."""

    def __init__(self):
        self._lock = threading.Lock()
        self._events = {}

    def reset(self):
        with self._lock:
            self._events.clear()

    def consume(self, user_id, action, limit, window_seconds, cost=1):
        """Record `cost` events. Return retry-after seconds, or 0 when allowed."""
        if cost < 1:
            cost = 1
        now = time.monotonic()
        key = (user_id, action)
        with self._lock:
            events = [stamp for stamp in self._events.get(key, []) if now - stamp < window_seconds]
            if len(events) + cost > limit:
                self._events[key] = events
                if not events:
                    return max(1, int(window_seconds))
                return max(1, int(window_seconds - (now - events[0])) + 1)
            events.extend([now] * cost)
            self._events[key] = events
            return 0


quota = QuotaTracker()


def authenticate_header(header_value):
    """Return a copy of the identity for a valid bearer token, else None."""
    if not isinstance(header_value, str):
        return None
    scheme, _, rest = header_value.partition(" ")
    if scheme != "Bearer":
        return None
    presented = rest.strip()
    if not presented or " " in presented or len(presented) > 512:
        return None

    presented_bytes = presented.encode("utf-8")
    match = None
    for token, identity in settings.identities.items():
        token_bytes = token.encode("utf-8")
        if len(token_bytes) != len(presented_bytes):
            continue
        if hmac.compare_digest(presented_bytes, token_bytes):
            match = identity
    if match is None:
        return None
    return {"user_id": match["user_id"], "tenant_id": match["tenant_id"]}


def collection_name_for_tenant(tenant_id):
    """Stable Milvus/Zilliz collection name that cannot collide across tenants."""
    digest = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"[^0-9A-Za-z]+", "_", tenant_id).strip("_")
    if not slug or not slug[0].isalpha():
        slug = "t" if not slug else f"t_{slug}"
    name = f"ring_{slug}_{digest}"[:255]
    if not _COLLECTION_NAME.fullmatch(name):
        name = f"ring_t_{digest}"
    return name


def is_safe_collection_name(name):
    return isinstance(name, str) and _COLLECTION_NAME.fullmatch(name) is not None
