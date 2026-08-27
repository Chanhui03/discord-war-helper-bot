from datetime import datetime

import pytest

from app.bot.commands.history import (
    detail_embed,
    has_records,
    list_embed,
    winner_of,
)
from app.database.repositories import (
    completed_matches,
    custom_position_stats,
    fill_match_records,
    finish_match,
    get_match,
)
from tests.test_repositories import game_for, named_match, staged_match

class TestListDisplay:
    def match(self, match_id, duration, team_a_score=1):
        from types import SimpleNamespace

        return SimpleNamespace(
            id=match_id,
            duration=duration,
            team_a_score=team_a_score,
            team_b_score=1 - team_a_score,
            created_at=datetime(2026, 8, 26, 21, 14),
        )

    def test_empty(self):
        assert "아직 끝난 내전이 없습니다." in list_embed([]).description

    def test_it_marks_which_matches_lack_a_replay_file(self):
        embed = list_embed([self.match(2, 1800), self.match(1, None)])
        lines = embed.description.split("\n")

        assert "전적파일 있음" in lines[0]
        assert "**전적파일 없음**" in lines[1]
        assert "1건은 개인 성적이 비어" in embed.footer.text

    def test_all_complete_matches_show_no_warning(self):
        embed = list_embed([self.match(1, 1800)])
        assert "비어 있습니다" not in embed.footer.text

    def test_winner_is_read_from_the_score(self):
        assert winner_of(self.match(1, None, team_a_score=1)) == "A"
        assert winner_of(self.match(1, None, team_a_score=0)) == "B"

    def test_has_records_follows_the_duration(self):
        assert has_records(self.match(1, 1800)) is True
        assert has_records(self.match(1, None)) is False

class TestFillRecords:
    async def button_only(self, session):
        """버튼으로만 확정해 개인 성적이 비어 있는 내전."""
        match = await staged_match(session, server_id=5)
        return await finish_match(session, match.id, "A")

    async def test_a_button_only_match_starts_empty(self, session):
        match = await self.button_only(session)
        assert match.duration is None
        assert all(entry.kills is None for entry in match.participants)
        assert await custom_position_stats(session, match.participants[0].player_id, 5) == []

    async def test_filling_adds_stats_without_touching_the_winner(self, session):
        match = await named_match(session)
        finished = await finish_match(session, match.id, "A")
        wins = {e.player_id: e.win for e in finished.participants}

        status, filled = await fill_match_records(
            session, match.id, game_for(match, winner="A")
        )

        assert status == "filled"
        assert filled.duration is not None
        assert any(entry.kills is not None for entry in filled.participants)
        assert {e.player_id: e.win for e in filled.participants} == wins

    async def test_it_feeds_the_line_stats_afterwards(self, session):
        """보완의 목적이다. 채우기 전에는 라인별 지표가 비어 있다."""
        match = await named_match(session, server_id=5)
        await finish_match(session, match.id, "A")
        player_id = match.participants[0].player_id
        assert await custom_position_stats(session, player_id, 5) == []

        await fill_match_records(session, match.id, game_for(match, winner="A"))
        assert await custom_position_stats(session, player_id, 5) != []

    async def test_a_file_from_another_game_is_refused(self, session):
        """승리 팀이 다르면 엉뚱한 경기다. 덮어쓰면 내전 승률까지 어긋난다."""
        match = await named_match(session)
        await finish_match(session, match.id, "A")

        status, filled = await fill_match_records(
            session, match.id, game_for(match, winner="B")
        )

        assert status == "conflict"
        assert filled is None

        stored = await get_match(session, match.id)
        assert stored.duration is None, "거절했는데 값이 들어갔다"
        assert all(e.kills is None for e in stored.participants)

    async def test_an_unfinished_match_is_refused(self, session):
        match = await staged_match(session)
        status, filled = await fill_match_records(
            session, match.id, game_for(match, winner="A")
        )
        assert (status, filled) == ("open", None)

    async def test_a_missing_match_is_refused(self, session):
        match = await named_match(session)
        status, _ = await fill_match_records(session, 9999, game_for(match))
        assert status == "missing"

    async def test_refilling_overwrites(self, session):
        """잘못 넣은 파일을 다시 올려 고칠 수 있어야 한다."""
        match = await named_match(session)
        await finish_match(session, match.id, "A")
        await fill_match_records(session, match.id, game_for(match, winner="A"))

        status, filled = await fill_match_records(
            session, match.id, game_for(match, winner="A")
        )
        assert status == "filled"

class TestCompletedMatches:
    async def test_only_finished_matches_of_this_server(self, session):
        first = await staged_match(session, server_id=5)
        await finish_match(session, first.id, "A")
        await staged_match(session, server_id=5)  # 아직 진행 중
        other = await staged_match(session, server_id=6)
        await finish_match(session, other.id, "B")

        found = await completed_matches(session, 5)
        assert [m.id for m in found] == [first.id]

    async def test_newest_first(self, session):
        ids = []
        for _ in range(3):
            match = await staged_match(session, server_id=5)
            await finish_match(session, match.id, "A")
            ids.append(match.id)

        found = await completed_matches(session, 5)
        assert [m.id for m in found] == sorted(ids, reverse=True)

    async def test_limit(self, session):
        for _ in range(3):
            match = await staged_match(session, server_id=5)
            await finish_match(session, match.id, "A")

        assert len(await completed_matches(session, 5, limit=2)) == 2
