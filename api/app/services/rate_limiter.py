import time
from typing import Optional, Tuple
from fastapi import HTTPException, status, Request
import redis.asyncio as redis

from app.config import settings


class RateLimiter:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None

    async def get_client(self) -> redis.Redis:
        if self.redis_client is None:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        return self.redis_client

    async def close(self):
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        client = await self.get_client()
        current_time = int(time.time())
        window_start = current_time - window_seconds

        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(current_time): current_time})
        pipe.expire(key, window_seconds)
        results = await pipe.execute()

        current_count = results[1]
        ttl = window_seconds - (current_time - (current_time % window_seconds))

        if current_count >= limit:
            return False, current_count, ttl

        return True, current_count + 1, ttl

    async def get_remaining(self, key: str, limit: int, window_seconds: int) -> int:
        client = await self.get_client()
        current_time = int(time.time())
        window_start = current_time - window_seconds
        count = await client.zcount(key, window_start, current_time)
        return max(0, limit - count)


rate_limiter = RateLimiter()


async def login_rate_limit(
    request: Request,
    email: str
) -> None:
    if settings.ENVIRONMENT == "test":
        return

    key = f"login_attempts:{email.lower()}"
    limit = settings.LOGIN_RATE_LIMIT
    window = settings.LOGIN_RATE_LIMIT_WINDOW_MINUTES * 60

    allowed, count, ttl = await rate_limiter.check_rate_limit(key, limit, window)

    if not allowed:
        retry_after = ttl
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {retry_after} seconds.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + ttl),
            }
        )

    request.state.rate_limit_remaining = limit - count
    request.state.rate_limit_reset = int(time.time()) + ttl


def add_rate_limit_headers(request: Request, response) -> None:
    if hasattr(request.state, "rate_limit_remaining"):
        response.headers["X-RateLimit-Limit"] = str(settings.LOGIN_RATE_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
        response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_reset)