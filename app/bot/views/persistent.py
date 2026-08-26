"""재시작 후에도 동작하는 버튼 뷰.

discord.py 는 custom_id 로 버튼을 다시 찾는다. 그래서 timeout 을 두지 않고
어느 내전의 버튼인지를 custom_id 에 담아, 봇이 다시 뜨면 그대로 등록한다.
"""

import discord


class PersistentView(discord.ui.View):
    """버튼마다 `PREFIX:<버튼 이름>:<내전 번호>` 형태의 custom_id 를 붙인다."""

    PREFIX = ""

    def __init__(self, match_id: int) -> None:
        super().__init__(timeout=None)
        self.match_id = match_id
        for item in self.children:
            item.custom_id = f"{self.PREFIX}:{item.custom_id}:{match_id}"
