# app/utils/rate_limit.py
"""
Límite de intentos por ventana de tiempo (inicio de sesión y registro), para
frenar a quien prueba contraseñas en masa o crea cuentas en serie.

Vive en memoria, como los locks de clase (services/locks.py): el backend
corre en un solo proceso, y si se reinicia los contadores vuelven a cero, lo
cual está bien para este propósito.
"""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class SlidingWindow:
    """Cuenta eventos por clave dentro de los últimos `window_s` segundos."""

    def __init__(self, window_s: float):
        self.window_s = window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _purge(self, key: str, now: float) -> deque:
        q = self._hits[key]
        while q and now - q[0] >= self.window_s:
            q.popleft()
        return q

    def count(self, key: str) -> int:
        with self._lock:
            return len(self._purge(key, time.monotonic()))

    def hit(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._purge(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def retry_after(self, key: str) -> float:
        """Segundos hasta que vence el evento más viejo de la clave."""
        with self._lock:
            q = self._purge(key, time.monotonic())
            return max(0.0, self.window_s - (time.monotonic() - q[0])) if q else 0.0


def client_ip(request: Request) -> str:
    """IP del cliente. En producción el backend solo es accesible a través
    del nginx del frontend, que reemplaza X-Real-IP con la IP real
    (frontend/nginx.prod.conf.template), así que se puede confiar en él."""
    return (request.headers.get("x-real-ip")
            or (request.client.host if request.client else None)
            or "desconocida").strip()


def too_many(window: SlidingWindow, key: str, limit: int, what: str) -> None:
    """429 con un mensaje en español si `key` ya llegó al límite."""
    if window.count(key) >= limit:
        minutes = max(1, math.ceil(window.retry_after(key) / 60))
        raise HTTPException(
            429,
            f"{what} Probá de nuevo en {minutes} minuto{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(minutes * 60)},
        )
