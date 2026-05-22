import os
from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock


_TEMP_ENV_LOCK = RLock()


@contextmanager
def temporary_env_api_key(env_name: str, user_api_key: str | None) -> Iterator[None]:
    """临时暴露一次请求携带的 API key。

    旧版/部分三方封装只能从环境变量读取 key。这里优先使用后端已配置的 env key；
    如果没有配置，才在加锁区间内把前端传来的临时 key 写入环境变量，调用结束后删除。
    """

    if os.environ.get(env_name) or not user_api_key:
        yield
        return

    with _TEMP_ENV_LOCK:
        os.environ[env_name] = user_api_key
        try:
            yield
        finally:
            os.environ.pop(env_name, None)
