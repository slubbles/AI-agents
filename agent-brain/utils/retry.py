"""
Retry Utility — Handles transient API errors

Provides a decorator and a wrapper for Claude API calls that:
- Retries on 529 Overloaded errors
- Retries on 429 Rate Limit errors
- Uses exponential backoff with jitter
- Configurable max attempts and base delay

Usage:
    from utils.retry import with_retry, retry_api_call, create_message

    # As decorator
    @with_retry(max_attempts=5, base_delay=30)
    def my_api_call():
        return client.messages.create(...)

    # As wrapper
    result = retry_api_call(lambda: client.messages.create(...))

    # As drop-in replacement for client.messages.create
    response = create_message(client, model=..., max_tokens=..., ...)
"""

import time
import random
import functools
from typing import Callable, TypeVar

T = TypeVar("T")

# Error strings that indicate transient/retryable failures
RETRYABLE_PATTERNS = [
    "overloaded",
    "529",
    "rate_limit",
    "rate limit",
    "too many requests",
    "503",
    "service unavailable",
]


def is_retryable(error: Exception) -> bool:
    """Check if an error is transient and worth retrying."""
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()
    return any(
        pattern in error_str or pattern in error_type
        for pattern in RETRYABLE_PATTERNS
    )


def retry_api_call(
    fn: Callable[[], T],
    max_attempts: int = 5,
    base_delay: float = 15.0,
    max_delay: float = 120.0,
    verbose: bool = True,
) -> T:
    """
    Execute a function with automatic retry on transient API errors.
    
    Args:
        fn: Zero-argument callable to execute
        max_attempts: Maximum number of attempts (default 5)
        base_delay: Initial delay in seconds (default 15)
        max_delay: Maximum delay between retries (default 120)
        verbose: Print retry messages (default True)
    
    Returns:
        Result of fn()
    
    Raises:
        The last exception if all attempts fail
    """
    last_error = None
    
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if not is_retryable(e):
                raise  # Non-retryable error, propagate immediately
            
            if attempt == max_attempts - 1:
                raise  # Last attempt, propagate
            
            # Exponential backoff with jitter
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 5), max_delay)
            if verbose:
                print(f"  [RETRY] {type(e).__name__}: waiting {delay:.0f}s "
                      f"(attempt {attempt + 1}/{max_attempts})...")
            time.sleep(delay)
    
    raise last_error  # Should never reach here, but just in case


def with_retry(
    max_attempts: int = 5,
    base_delay: float = 15.0,
    max_delay: float = 120.0,
    verbose: bool = True,
):
    """
    Decorator version of retry_api_call.
    
    Usage:
        @with_retry(max_attempts=3)
        def call_claude():
            return client.messages.create(...)
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return retry_api_call(
                lambda: fn(*args, **kwargs),
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                verbose=verbose,
            )
        return wrapper
    return decorator


def create_message(client, *, max_attempts: int = 5, base_delay: float = 15.0,
                   verbose: bool = True, **kwargs):
    """
    Drop-in replacement for client.messages.create() with automatic retry.
    
    Usage:
        from utils.retry import create_message
        response = create_message(client, model="...", max_tokens=4096,
                                  system="...", messages=[...])
    
    All keyword arguments are forwarded to client.messages.create().
    """
    return retry_api_call(
        lambda: client.messages.create(**kwargs),
        max_attempts=max_attempts,
        base_delay=base_delay,
        verbose=verbose,
    )
