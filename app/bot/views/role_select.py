from typing import Optional

import discord

from app.database.repositories import set_role_preference
from app.database.session import session_factory
from app.roles import ROLE_LABELS, ROLES

NO_ROLE = "NONE"

FIELDS = (
    ("main_role", "선호라인 1순위"),
    ("secondary_role", "선호라인 2순위"),
    ("avoid_role", "기피라인"),
)

def label_of(role: Optional[str]) -> str:
    return ROLE_LABELS.get(role, "없음")

def describe(main_role, secondary_role, avoid_role) -> str:
    return (
        f"선호 1순위 **{label_of(main_role)}** / "
        f"선호 2순위 **{label_of(secondary_role)}** / "
        f"기피 **{label_of(avoid_role)}**\n"
        "-# 기피라인을 간 다음 내전에서는 그 라인에 배정되지 않습니다."
    )

class RoleSelect(discord.ui.Select):
    def __init__(self, field: str, title: str, current: Optional[str]) -> None:
        # 고르고 나면 placeholder 가 사라져 세 박스가 모두 같아 보인다. 라벨에
        # 항목 이름을 붙여 접힌 상태에서도 무슨 라인을 고르는 칸인지 알게 한다.
        options = [
            discord.SelectOption(
                label=f"{title} · 없음", value=NO_ROLE, default=current is None
            )
        ] + [
            discord.SelectOption(
                label=f"{title} · {ROLE_LABELS[role]}",
                value=role,
                default=role == current,
            )
            for role in ROLES
        ]
        super().__init__(
            placeholder=f"{title} 선택", min_values=1, max_values=1, options=options
        )
        self.field = field
        self.title = title

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "RolePreferenceView" = self.view
        role = None if self.values[0] == NO_ROLE else self.values[0]

        planned = dict(view.selection())
        planned[self.field] = role
        chosen = [value for value in planned.values() if value is not None]
        if len(chosen) != len(set(chosen)):
            await interaction.response.send_message(
                "선호라인 1순위 / 2순위 / 기피라인은 서로 다르게 선택해주세요.", ephemeral=True
            )
            return

        async with session_factory() as session:
            await set_role_preference(session, view.discord_id, self.field, role)

        setattr(view, self.field, role)
        view.refresh_defaults()
        await interaction.response.edit_message(
            content=describe(**view.selection()), view=view
        )

class RolePreferenceView(discord.ui.View):
    def __init__(
        self, discord_id: int, main_role, secondary_role, avoid_role
    ) -> None:
        super().__init__(timeout=180)
        self.discord_id = discord_id
        self.main_role = main_role
        self.secondary_role = secondary_role
        self.avoid_role = avoid_role
        for field, title in FIELDS:
            self.add_item(RoleSelect(field, title, getattr(self, field)))

    def selection(self):
        return {field: getattr(self, field) for field, _ in FIELDS}

    def refresh_defaults(self) -> None:
        """선택 후에도 현재 값이 표시되도록 default 를 갱신한다."""
        for item in self.children:
            current = getattr(self, item.field)
            for option in item.options:
                option.default = (
                    current is None if option.value == NO_ROLE else option.value == current
                )
