import os
from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock


_TEMP_ENV_LOCK = RLock()


@contextmanager
def temporary_env_api_key(env_name: str, user_api_key: str | None) -> Iterator[None]:
    """Prefer configured env keys, otherwise expose a request key briefly."""

    if os.environ.get(env_name) or not user_api_key:
        yield
        return

    with _TEMP_ENV_LOCK:
        os.environ[env_name] = user_api_key
        try:
            yield
        finally:
            os.environ.pop(env_name, None)
