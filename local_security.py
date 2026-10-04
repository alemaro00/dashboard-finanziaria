"""Same-origin boundary for the single-user loopback service; not a remote IAM."""
import hmac
import math
import time
from collections import deque
from threading import Lock
from urllib.parse import urlsplit


class RequestGuard:
    def __init__(self):
        self._events: deque[float] = deque()
        self._lock = Lock()

    def allowed(self, headers, port):
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if headers.get('Host', '') not in hosts:
            return False
        origin = headers.get('Origin')
        if origin is not None and origin not in {f'http://{h}' for h in hosts}:
            return False
        if origin and urlsplit(origin).netloc != headers.get('Host'):
            return False
        if headers.get('Sec-Fetch-Site', '') not in ('', 'none', 'same-origin'):
            return False
        return True

    def allowed_callback(self, headers, port):
        """Allow only the provider's GET redirect to the exact loopback listener."""
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if headers.get('Host', '') not in hosts:
            return False
        if headers.get('Origin') is not None:
            return False
        return headers.get('Sec-Fetch-Mode', '') in ('', 'navigate')

    def admit(self):
        with self._lock:
            now = time.monotonic()
            while self._events and self._events[0] <= now - 60:
                self._events.popleft()
            if len(self._events) >= 600:
                return False
            self._events.append(now)
            return True


def verify_csrf(expected, provided):
    return isinstance(provided, str) and hmac.compare_digest(expected, provided)


def validate_json_tree(value, depth=0):
    if depth > 24:
        raise ValueError('JSON troppo annidato')
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Numero non finito')
    if isinstance(value, dict):
        if len(value) > 10000:
            raise ValueError('Troppi campi')
        for key, item in value.items():
            if len(key) > 256:
                raise ValueError('Nome campo troppo lungo')
            validate_json_tree(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 10000:
            raise ValueError('Troppi elementi')
        for item in value:
            validate_json_tree(item, depth + 1)
    elif isinstance(value, str) and len(value) > 100000:
        raise ValueError('Testo troppo lungo')
