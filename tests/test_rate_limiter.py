"""
Regression test for the login rate limiter retry-after bug.

History: the Retry-After value returned with HTTP 429 responses was a huge
NEGATIVE number (e.g. -1790420400) because check_rate_limit computed
  ttl = window_seconds - (current_time - (current_time % window_seconds)),
which subtracts an epoch timestamp from the window. The correct value is
  ttl = window_seconds - (current_time % window_seconds),
hard-clamped to [1, window_seconds].

These tests deliberately exceed the limit and assert every retry-after seen
is a small positive number within the configured window.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

import time
import pytest
from fastapi import HTTPException


@pytest.fixture
def fake_limiter():
    """RateLimiter wired to an in-memory fake Redis (no live services)."""
    from fakeredis.aioredis import FakeRedis
    from app.services import rate_limiter as rl_module

    limiter = rl_module.RateLimiter()
    limiter.redis_client = FakeRedis(decode_responses=True)
    return limiter


@pytest.mark.asyncio
async def test_ttl_always_small_positive(fake_limiter):
    """Hammer the limiter and assert ttl stays within [1, window]."""
    window = 900
    key = f"test:ttl:{int(time.time() * 1000)}"
    for _ in range(10):
        allowed, count, ttl = await fake_limiter.check_rate_limit(key, 3, window)
        assert 1 <= ttl <= window, f"ttl out of range: {ttl}"
    await fake_limiter.close()


@pytest.mark.asyncio
async def test_blocked_attempt_returns_small_positive_ttl(fake_limiter):
    """After exceeding the limit, the blocked response carries usable ttl."""
    window = 60
    key = f"test:blocked:{int(time.time() * 1000)}"
    # Limit 1: first attempt allowed, second denied (same-second attempts
    # share one sorted-set member, so limit=1 trips deterministically).
    allowed, _, ttl = await fake_limiter.check_rate_limit(key, 1, window)
    assert allowed is True
    assert 1 <= ttl <= window, f"ttl out of range: {ttl}"
    allowed, count, ttl = await fake_limiter.check_rate_limit(key, 1, window)
    assert allowed is False, f"expected denial, got allowed with count={count}"
    assert 1 <= ttl <= window, f"blocked ttl out of range: {ttl}"
    await fake_limiter.close()


@pytest.mark.asyncio
async def test_login_rate_limit_429_headers_positive(fake_limiter, monkeypatch):
    """End-to-end through login_rate_limit: 429 Retry-After in [1, window]."""
    from app.services import rate_limiter as rl_module
    from app.services.rate_limiter import login_rate_limit

    monkeypatch.setattr(rl_module, "rate_limiter", fake_limiter)
    monkeypatch.setattr(rl_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(rl_module.settings, "LOGIN_RATE_LIMIT", 1)
    monkeypatch.setattr(rl_module.settings, "LOGIN_RATE_LIMIT_WINDOW_MINUTES", 1)

    class FakeRequest:
        def __init__(self):
            from types import SimpleNamespace
            self.state = SimpleNamespace()
            self.client = SimpleNamespace(host="127.0.0.1")

    window = 60
    seen_429 = False
    for _ in range(6):
        try:
            await login_rate_limit(FakeRequest(), "RateTest@Example.com")
        except HTTPException as exc:
            assert exc.status_code == 429
            retry_after = int(exc.headers["Retry-After"])
            assert 1 <= retry_after <= window, f"Retry-After out of range: {retry_after}"
            assert "Try again in -" not in exc.detail, f"negative retry-after leaked: {exc.detail}"
            seen_429 = True
    assert seen_429, "rate limit was never triggered"
    await fake_limiter.close()
