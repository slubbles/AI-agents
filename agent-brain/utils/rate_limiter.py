"""
Global Rate Limiter -- Token bucket rate limiting for external API calls.

Prevents hitting rate limits on DuckDuckGo, page fetching, and other
external services across multiple runs in rapid succession.

Each resource type (search, fetch) has its own bucket with configurable
rate (calls per minute). Thread-safe.

Usage:
    from utils.rate_limiter import wait_for_slot

    wait_for_slot("search")   # blocks until a search slot is available
    results = web_search(query)
"""

import time
import threading
from collections import defaultdict


class _TokenBucket:
    """Token bucket rate limiter for a single resource."""

    def __init__(self, rate_per_minute: float):
        self.rate = rate_per_minute / 60.0  # tokens per second
        self.capacity = rate_per_minute      # max burst
        self.tokens = rate_per_minute        # start full
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def acquire(self, timeout: float = 30.0) -> bool:
        """Wait for a token. Returns True if acquired, False if timed out."""
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True
            # No token available, wait
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            # Sleep until next token is expected
            with self.lock:
                wait_time = (1.0 - self.tokens) / self.rate if self.rate > 0 else 1.0
            time.sleep(min(wait_time, remaining, 1.0))

    def update_rate(self, rate_per_minute: float):
        """Update the rate limit."""
        with self.lock:
            self.rate = rate_per_minute / 60.0
            self.capacity = rate_per_minute


# Registry of buckets by resource name
_buckets: dict[str, _TokenBucket] = {}
_registry_lock = threading.Lock()

# Default rates (overridden by config values)
_default_rates = {
    "search": 15,   # web searches per minute
    "fetch": 20,    # page fetches per minute
    "browser": 10,  # browser fetches per minute
}


def _get_bucket(resource: str) -> _TokenBucket:
    """Get or create a bucket for a resource type."""
    with _registry_lock:
        if resource not in _buckets:
            rate = _default_rates.get(resource, 30)
            # Try to load from config
            try:
                from config import RATE_LIMIT_SEARCHES_PER_MINUTE, RATE_LIMIT_FETCHES_PER_MINUTE
                config_rates = {
                    "search": RATE_LIMIT_SEARCHES_PER_MINUTE,
                    "fetch": RATE_LIMIT_FETCHES_PER_MINUTE,
                    "browser": RATE_LIMIT_FETCHES_PER_MINUTE,
                }
                rate = config_rates.get(resource, rate)
            except ImportError:
                pass
            _buckets[resource] = _TokenBucket(rate)
        return _buckets[resource]


def wait_for_slot(resource: str, timeout: float = 30.0) -> bool:
    """
    Wait for a rate limit slot to become available.

    Args:
        resource: Resource type (search, fetch, browser)
        timeout: Max seconds to wait (default 30)

    Returns:
        True if slot acquired, False if timed out
    """
    bucket = _get_bucket(resource)
    return bucket.acquire(timeout)


def check_slot(resource: str) -> bool:
    """Check if a slot is available without waiting."""
    bucket = _get_bucket(resource)
    with bucket.lock:
        bucket._refill()
        return bucket.tokens >= 1.0


def get_status() -> dict:
    """Get current rate limiter status for all resources."""
    status = {}
    with _registry_lock:
        for name, bucket in _buckets.items():
            with bucket.lock:
                bucket._refill()
                status[name] = {
                    "tokens_available": round(bucket.tokens, 1),
                    "capacity": bucket.capacity,
                    "rate_per_minute": round(bucket.rate * 60, 1),
                }
    return status


def reset(resource: str = None):
    """Reset a specific bucket or all buckets to full capacity."""
    with _registry_lock:
        if resource:
            if resource in _buckets:
                bucket = _buckets[resource]
                with bucket.lock:
                    bucket.tokens = bucket.capacity
                    bucket.last_refill = time.monotonic()
        else:
            for bucket in _buckets.values():
                with bucket.lock:
                    bucket.tokens = bucket.capacity
                    bucket.last_refill = time.monotonic()
