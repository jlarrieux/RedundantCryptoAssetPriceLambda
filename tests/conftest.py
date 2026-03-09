import sys
from unittest.mock import MagicMock

# aioredis 2.0.1 is broken on Python >= 3.11 (duplicate TimeoutError base).
# Production runs Python 3.10 in Docker. Provide a mock so modules that
# import aioredis can be collected on newer interpreters.
try:
    import aioredis  # noqa: F401
except (ImportError, TypeError):
    sys.modules['aioredis'] = MagicMock()
