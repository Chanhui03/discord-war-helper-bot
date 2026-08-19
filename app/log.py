"""설계서 12장의 구조화 로그.

메시지를 `이벤트명 key=value ...` 형태로 남겨 나중에 grep/파싱하기 쉽게 한다.
"""

import logging

def _fields(fields: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in fields.items())

def event(logger: logging.Logger, name: str, **fields) -> None:
    logger.info("%s %s", name, _fields(fields))

def warn(logger: logging.Logger, name: str, **fields) -> None:
    logger.warning("%s %s", name, _fields(fields))
