import discord

from app.database.repositories import set_role_preference
from app.database.session import session_factory
from app.roles import ROLE_LABELS, ROLES

def describe(main_role, secondary_role) -> str:
    main = ROLE_LABELS.get(main_role, "미설정")
    secondary = ROLE_LABELS.get(secondary_role, "미설정")
    return f"주라인: **{main}** / 부라인: **{secondary}**"

class RoleSelect(discord.ui.Select):
    def __init__(self, field: str, placeholder: str) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=ROLE_LABELS[role], value=role)
                for role in ROLES
            ],
        )
        self.field = field

    async def callback(self, interaction: discord.Interaction) -> None:
        view: "RolePreferenceView" = self.view
        role = self.values[0]

        other = (
            view.secondary_role if self.field == "main_role" else view.main_role
        )
        if role == other:
            await interaction.response.send_message(
                "주라인과 부라인은 다르게 선택해주세요.", ephemeral=True
            )
            return

        async with session_factory() as session:
            await set_role_preference(session, view.discord_id, self.field, role)

        setattr(view, self.field, role)
        await interaction.response.edit_message(
            content=describe(view.main_role, view.secondary_role), view=view
        )

class RolePreferenceView(discord.ui.View):
    def __init__(self, discord_id: int, main_role, secondary_role) -> None:
        super().__init__(timeout=180)
        self.discord_id = discord_id
        self.main_role = main_role
        self.secondary_role = secondary_role
        self.add_item(RoleSelect("main_role", "주라인 선택"))
        self.add_item(RoleSelect("secondary_role", "부라인 선택"))
