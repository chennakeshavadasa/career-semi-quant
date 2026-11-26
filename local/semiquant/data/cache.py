"""Thread-safe TTL memo cache with single-flight loading and an optional disk layer.

* ``cached(key, ttl, loader)`` returns a fresh value, loading it at most once at a time
  per key (concurrent callers wait for the same load instead of hitting Yahoo twice).
* With ``disk=True`` the value is also pickled under ~/.semiquant/cache so a restart is
  instant, and if Yahoo fails (rate limit, outage) the last good value is served and
  flagged through ``last_error``/``is_stale`` instead of raising.
"""
from __future__ import annotations

import hashlib
import os
import pickle
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from .. import config

_MAX_ENTRIES = 4000
_store: "OrderedDict[str, tuple[float, float, Any]]" = OrderedDict()  # key -> (stored_at, ttl, value)
_store_lock = threading.Lock()
_key_locks: dict[str, threading.Lock] = {}
_stale: dict[str, str] = {}
stats = {"hits": 0, "misses": 0, "disk_hits": 0, "stale_served": 0, "errors": 0}


def _lock_for(key: str) -> threading.Lock:
    with _store_lock:
        lk = _key_locks.get(key)
        if lk is None:
            lk = _key_locks[key] = threading.Lock()
        return lk


def _disk_path(key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]
    return os.path.join(str(config.CACHE_DIR), f"{h}.pkl")


def _disk_load(key: str) -> tuple[float, Any] | None:
    try:
        with open(_disk_path(key), "rb") as f:
            stored_key, stored_at, value = pickle.load(f)
        return (stored_at, value) if stored_key == key else None
    except Exception:  # noqa: BLE001 - missing / corrupt / incompatible pickle
        return None


def _disk_save(key: str, stored_at: float, value: Any) -> None:
    try:
        config.ensure_dirs()
        p = _disk_path(key)
        tmp = p + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump((key, stored_at, value), f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, p)
    except Exception:  # noqa: BLE001 - the disk layer is best-effort
        pass


def peek(key: str) -> Any | None:
    """Value if present in memory (fresh or not), without loading."""
    with _store_lock:
        e = _store.get(key)
    return e[2] if e else None


def age(key: str) -> float | None:
    with _store_lock:
        e = _store.get(key)
    return time.time() - e[0] if e else None


def is_stale(key: str) -> bool:
    return key in _stale


def last_error(key: str) -> str | None:
    return _stale.get(key)


def put(key: str, value: Any, ttl: float, disk: bool = False) -> None:
    now = time.time()
    with _store_lock:
        _store[key] = (now, ttl, value)
        _store.move_to_end(key)
        while len(_store) > _MAX_ENTRIES:
            _store.popitem(last=False)
    _stale.pop(key, None)
    if disk:
        _disk_save(key, now, value)


def invalidate(prefix: str = "") -> int:
    with _store_lock:
        keys = [k for k in _store if k.startswith(prefix)]
        for k in keys:
            del _store[k]
    return len(keys)


def cached(key: str, ttl: float, loader: Callable[[], Any], disk: bool = False,
           accept: Callable[[Any], bool] | None = None) -> Any:
    """Return the cached value for ``key`` if younger than ``ttl`` s, else load it.

    ``accept(value)`` can reject a loaded value (e.g. an empty frame) so the previous
    good value is kept. On loader failure the last good value (memory, then disk) is
    returned; if there is none the exception propagates.
    """
    now = time.time()
    with _store_lock:
        e = _store.get(key)
    if e and now - e[0] < ttl:
        stats["hits"] += 1
        return e[2]
    with _lock_for(key):
        with _store_lock:  # another thread may have loaded it while we waited
            e = _store.get(key)
        if e and time.time() - e[0] < ttl:
            stats["hits"] += 1
            return e[2]
        if e is None and disk:
            d = _disk_load(key)
            if d and time.time() - d[0] < ttl:
                stats["disk_hits"] += 1
                with _store_lock:
                    _store[key] = (d[0], ttl, d[1])
                return d[1]
        stats["misses"] += 1
        try:
            value = loader()
            if accept is not None and not accept(value):
                raise ValueError("loader returned an unusable value")
        except Exception as exc:  # noqa: BLE001
            stats["errors"] += 1
            fallback = e[2] if e else None
            if fallback is None and disk:
                d = _disk_load(key)
                fallback = d[1] if d else None
            if fallback is not None:
                stats["stale_served"] += 1
                _stale[key] = f"{type(exc).__name__}: {exc}"[:300]
                return fallback
            raise
        put(key, value, ttl, disk=disk)
        return value
