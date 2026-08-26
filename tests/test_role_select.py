from app.bot.views.role_select import NO_ROLE, RolePreferenceView

def selects(view):
    return {item.field: item for item in view.children}


def test_every_option_says_which_line_it_sets():
    """접힌 박스에는 고른 옵션의 라벨만 보이므로 라벨에 항목 이름이 있어야 한다."""
    view = RolePreferenceView(1, main_role="MID", secondary_role=None, avoid_role=None)
    main = selects(view)["main_role"]

    assert [option.label for option in main.options] == [
        "선호라인 1순위 · 없음",
        "선호라인 1순위 · 탑",
        "선호라인 1순위 · 정글",
        "선호라인 1순위 · 미드",
        "선호라인 1순위 · 원딜",
        "선호라인 1순위 · 서폿",
    ]
    assert [option.label for option in selects(view)["avoid_role"].options][:2] == [
        "기피라인 · 없음",
        "기피라인 · 탑",
    ]


def test_current_choice_is_the_default_option():
    view = RolePreferenceView(1, main_role="MID", secondary_role=None, avoid_role=None)
    main, secondary = selects(view)["main_role"], selects(view)["secondary_role"]

    assert [o.value for o in main.options if o.default] == ["MID"]
    assert [o.value for o in secondary.options if o.default] == [NO_ROLE]
