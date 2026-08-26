from app.bot.commands.profile import rank_icon
from app.services.scoring import APEX_TIERS, TIER_ORDER

def test_every_tier_has_its_own_emblem():
    for tier in TIER_ORDER + APEX_TIERS:
        emblem = rank_icon(tier)
        assert emblem.name == f"{tier.lower()}.png"
        assert emblem.exists(), f"{tier} 엠블럼 파일이 없다"

def test_lowercase_and_unranked_are_handled():
    assert rank_icon("gold").name == "gold.png"
    assert rank_icon(None).name == "unranked.png"
    assert rank_icon("").name == "unranked.png"

def test_unknown_tier_falls_back_to_unranked():
    assert rank_icon("SUPERMASTER").name == "unranked.png"
