"""구조화 로그. 이벤트 이름과 필드 이름이 부딪히지 않아야 한다."""

import logging

from app.log import event, warn

def line(caplog):
    [record] = caplog.records
    return record.getMessage()

def test_fields_are_written_as_key_value(caplog):
    log = logging.getLogger("t")
    with caplog.at_level(logging.INFO, logger="t"):
        event(log, "command", user=1, guild=2)
    assert line(caplog) == "command user=1 guild=2"

def test_a_field_may_be_called_name(caplog):
    """이름이 name 인 필드를 막으면 명령 이름을 남길 수가 없다.

    예전에는 event(log, "command", name=...) 가 TypeError 로 터져서 명령
    로그가 한 줄도 남지 않았다.
    """
    log = logging.getLogger("t")
    with caplog.at_level(logging.INFO, logger="t"):
        event(log, "command", name="/내점수", user=1)
    assert line(caplog) == "command name=/내점수 user=1"

def test_warn_takes_the_same_shape(caplog):
    log = logging.getLogger("t")
    with caplog.at_level(logging.WARNING, logger="t"):
        warn(log, "riot_error", name="lookup", status=429)
    assert line(caplog) == "riot_error name=lookup status=429"
