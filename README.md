# 내전 도우미

LoL 내전 참가자를 모아 5:5 팀을 자동으로 짜주는 Discord 봇. 내 PC에서 직접 돌린다.

## 준비

Python 3.9 이상. 저장소 루트에서:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

`.env.example`을 `.env`로 복사해 채운다.

```bash
cp .env.example .env
```

| 항목 | 설명 |
|---|---|
| `DISCORD_TOKEN` | [Discord 개발자 포털](https://discord.com/developers/applications)의 봇 토큰 |
| `RIOT_API_KEY` | [Riot 개발자 포털](https://developer.riotgames.com). 개발용 키는 24시간마다 만료되므로 `/등록`이 하루 뒤 실패하면 새로 발급받는다 |
| `DISCORD_GUILD_ID` | 슬래시 명령을 즉시 등록할 서버 ID. 쉼표로 여러 개. 비우면 전역 등록이라 반영에 최대 1시간 걸린다 |

## 실행

```bash
venv/bin/python -m app.main
```

`내전도우미#8506 로그인 완료`가 보이면 성공. Discord에서 `/ping`으로 확인한다.

DB는 저장소 루트의 `war_helper.db`(SQLite) 하나다. 첫 실행 때 자동으로 만들어지고,
이후 기동할 때마다 스키마를 최신으로 맞춘다. 별도 설치가 필요 없다.

끄려면 `Ctrl+C`. **봇은 이 프로세스가 떠 있는 동안에만 응답한다** — 내전을 할 때 켜두면 된다.
껐다 켜도 기록은 남고, 진행 중이던 내전의 버튼도 다시 살아난다(`restore_views()`).

## 명령

| 명령 | 하는 일 |
|---|---|
| `/등록 게임이름#태그` | Riot 계정을 연결하고 랭크·최근 20경기를 받아온다 |
| `/라인` | 주라인 / 부라인 / 기피 라인을 고른다 |
| `/전적` | 저장된 전적과 라인별 지표를 본다 |
| `/내전` | 참가자를 모집한다 (서버 관리 권한 필요) |
| `/결과` | 승리 팀을 확정한다 (서버 관리 권한 필요) |
| `/ping` | 응답 속도 확인 |

## 개발

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest
```

테스트는 인메모리 SQLite를 쓰므로 `.env` 없이도 돌아간다.

스키마를 바꿨으면 마이그레이션을 만든다:

```bash
venv/bin/alembic revision --autogenerate -m "설명"
```

## 문제가 생기면

| 증상 | 확인 |
|---|---|
| 기동하자마자 `ValidationError` | `.env`에 `DISCORD_TOKEN` / `RIOT_API_KEY`가 있는지 |
| 슬래시 명령이 안 보임 | `.env`의 `DISCORD_GUILD_ID`에 해당 서버 ID가 있는지, 봇이 그 서버에 초대됐는지 |
| 명령이 두 번 응답 | 같은 토큰으로 봇이 두 곳에서 켜져 있다 |
| `/등록`만 실패 | Riot 키 만료. 개발용 키는 24시간마다 갱신해야 한다 |
