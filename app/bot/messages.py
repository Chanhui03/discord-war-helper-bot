"""여러 곳에서 쓰는 사용자 안내 문구.

같은 문구가 명령과 버튼 양쪽에 흩어져 있어 한쪽만 고치기 쉬웠다.
"""

NEED_REGISTER = "먼저 `/전적등록`으로 Riot 계정을 연결해주세요."

def need_manage_guild(action: str) -> str:
    """action 은 조사 '은' 이 붙는 명사구. 예: "내전 생성"."""
    return f"{action}은 서버 관리 권한이 있는 사람만 할 수 있습니다."
