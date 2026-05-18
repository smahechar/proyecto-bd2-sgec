"""
app/extensions.py
Shared Flask extensions (instantiated here, init_app() called in factory).

Rate limiting strategy
──────────────────────
  /auth  (login)   → 5 attempts per 15 min  (brute-force guard)
  /api/register    → 10 per hour             (spam guard)
  everything else  → 200/day, 50/hour        (general abuse protection)

Storage: in-memory (single process). For multi-worker deployments replace
with Redis: FlaskLimiter(storage_uri="redis://localhost:6379").
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    # storage_uri="redis://localhost:6379",   # uncomment for multi-worker
)
