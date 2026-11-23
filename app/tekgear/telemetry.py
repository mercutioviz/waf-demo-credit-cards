"""In-memory telemetry powering the /ops dashboard.

State is per-process and deliberately not persisted. An SA needs a demo run to
zero instantly between attempts, and nothing recorded here is worth surviving a
restart.
"""

import json
import queue
import threading
import time
from collections import deque

RECENT_LIMIT = 200
RATE_WINDOW_SECONDS = 10
SUBSCRIBER_BACKLOG = 64

_UA_SIGNATURES = (
    ("python-requests", "python-requests"),
    ("httpx", "python-httpx"),
    ("aiohttp", "python-aiohttp"),
    ("curl", "curl"),
    ("go-http-client", "go-http"),
    ("headlesschrome", "headless-chrome"),
    ("playwright", "playwright"),
)


def classify_user_agent(user_agent):
    lowered = (user_agent or "").lower()
    if not lowered:
        return "none"
    for needle, label in _UA_SIGNATURES:
        if needle in lowered:
            return label
    if "chrome" in lowered or "firefox" in lowered or "safari" in lowered:
        return "browser"
    return "other"


class Telemetry:
    def __init__(self):
        self._lock = threading.Lock()
        self._sub_lock = threading.Lock()
        self._subscribers = []
        self._clear()

    def _clear(self):
        with self._lock:
            self._total = 0
            self._approved = 0
            self._declined = 0
            self._by_code = {}
            self._recent = deque(maxlen=RECENT_LIMIT)
            self._live_cards = []
            self._client_ips = set()
            self._bins = set()
            self._sessions = set()
            self._timestamps = deque()
            self._started = time.time()

    def reset(self):
        self._clear()
        self._publish({"type": "reset", "stats": self.stats()})

    def record(self, pan, masked, approved, code, client_ip, user_agent, session_id):
        now = time.time()
        entry = {
            "ts": now,
            "pan": masked,
            "bin": pan[:6],
            "approved": approved,
            "code": code,
            "ip": client_ip,
            "ua": classify_user_agent(user_agent),
            "session": session_id[:8] if session_id else None,
        }

        with self._lock:
            self._total += 1
            if approved:
                self._approved += 1
                if masked not in self._live_cards:
                    self._live_cards.append(masked)
            else:
                self._declined += 1
            self._by_code[code] = self._by_code.get(code, 0) + 1
            self._recent.appendleft(entry)
            self._client_ips.add(client_ip)
            self._bins.add(pan[:6])
            if session_id:
                self._sessions.add(session_id)
            self._timestamps.append(now)
            self._trim_locked(now)
            stats = self._stats_locked(now)

        self._publish({"type": "attempt", "attempt": entry, "stats": stats})

    def _trim_locked(self, now):
        cutoff = now - RATE_WINDOW_SECONDS
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def _stats_locked(self, now):
        window = min(RATE_WINDOW_SECONDS, max(now - self._started, 1.0))
        return {
            "total": self._total,
            "approved": self._approved,
            "declined": self._declined,
            "rate": round(len(self._timestamps) / window, 1),
            "unique_ips": len(self._client_ips),
            "unique_bins": len(self._bins),
            "unique_sessions": len(self._sessions),
            "by_code": dict(self._by_code),
            "live_cards": list(self._live_cards),
            "elapsed": round(now - self._started, 1),
        }

    def stats(self):
        now = time.time()
        with self._lock:
            self._trim_locked(now)
            return self._stats_locked(now)

    def snapshot(self):
        now = time.time()
        with self._lock:
            self._trim_locked(now)
            return {"stats": self._stats_locked(now), "recent": list(self._recent)}

    def subscribe(self):
        channel = queue.Queue(maxsize=SUBSCRIBER_BACKLOG)
        with self._sub_lock:
            self._subscribers.append(channel)
        return channel

    def unsubscribe(self, channel):
        with self._sub_lock:
            if channel in self._subscribers:
                self._subscribers.remove(channel)

    def _publish(self, payload):
        message = json.dumps(payload)
        with self._sub_lock:
            targets = list(self._subscribers)
        for channel in targets:
            try:
                channel.put_nowait(message)
            except queue.Full:
                # A dashboard that cannot keep up loses events rather than
                # back-pressuring the checkout path the demo is measuring.
                pass
