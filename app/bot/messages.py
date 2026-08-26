"""여러 곳에서 쓰는 사용자 안내 문구.

같은 문구가 명령과 버튼 양쪽에 흩어져 있어 한쪽만 고치기 쉬웠다.
"""

NEED_REGISTER = "먼저 `/전적등록`으로 Riot 계정을 연결해주세요."

# 임베드 설명 길이 제한에 걸리지 않도록 한 번에 보여줄 인원을 제한한다.
LIST_LIMIT = 40


def numbered(items, line) -> str:
    """1번부터 번호를 붙인 목록. 너무 길면 자르고 남은 수만 알린다."""
    lines = [
        f"{index}. {line(item)}"
        for index, item in enumerate(items[:LIST_LIMIT], 1)
    ]
    if len(items) > LIST_LIMIT:
        lines.append(f"-# 외 {len(items) - LIST_LIMIT}명")
    return "\n".join(lines)
