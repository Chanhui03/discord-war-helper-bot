# Oracle Cloud 배포

Always Free ARM VM 한 대에 봇과 Postgres를 함께 올린다. 비용 0원.

## 0. 사전 확인

- **Riot API 키**: 개발용 키는 24시간마다 만료된다. 클라우드에 올리면 하루 뒤 `/등록`이
  전부 실패하므로, [Riot 개발자 포털](https://developer.riotgames.com)에서
  Personal 또는 Production 키를 먼저 발급받는다.
- **봇을 로컬과 서버에서 동시에 켜지 않는다.** 같은 토큰으로 두 세션이 붙으면
  모든 명령에 두 번 응답한다.

## 1. VM 생성

Oracle Cloud 콘솔 → Compute → Instances → Create instance

| 항목 | 값 |
|---|---|
| Image | Ubuntu 24.04 (aarch64) |
| Shape | `VM.Standard.A1.Flex` |
| OCPU / Memory | **2 OCPU / 12 GB 이하** |
| SSH key | 공개키 등록 (또는 새로 생성해 개인키 다운로드) |

> Oracle이 2026-06-15부로 Always Free 한도를 4 OCPU/24GB에서 **2 OCPU/12GB로 낮췄다.**
> 초과 인스턴스는 2026-08-18부터 종료 대상이므로 반드시 한도 안에서 만든다.
> 이 봇에는 2 OCPU/12GB로 충분하다.

**Networking**: 인바운드로 열 포트는 **22(SSH)뿐**이다. 봇은 Discord와 Riot에
바깥으로 나가기만 하므로 웹 포트를 열 필요가 없다. Postgres(5432)는 절대 열지 않는다 —
`docker-compose.yml`이 루프백에만 바인딩하지만, 보안 목록에서도 닫아둔다.

## 2. Docker 설치

```bash
ssh ubuntu@<VM_공개_IP>

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu
sudo systemctl enable --now docker   # 재부팅 후 자동 시작
exit                                  # 그룹 반영을 위해 재접속
```

## 3. 코드 내려받기

```bash
ssh ubuntu@<VM_공개_IP>
git clone https://github.com/Chanhui03/discord-war-helper-bot.git
cd discord-war-helper-bot
```

## 4. `.env` 작성

`.env`는 저장소에 없다(gitignore). 서버에서 직접 만든다.

```bash
cat > .env <<'EOF'
DISCORD_TOKEN=<봇 토큰>
RIOT_API_KEY=<Riot 키>
DISCORD_GUILD_ID=1539176243382059101,561844449236484128
POSTGRES_PASSWORD=<강한 비밀번호>
EOF
chmod 600 .env
```

`DATABASE_URL`은 적지 않는다. `docker-compose.yml`이 `POSTGRES_PASSWORD`를 써서
컨테이너 네트워크용 주소를 자동으로 만든다. DB와 봇 양쪽이 같은 변수를 보므로
비밀번호가 어긋날 일이 없다.

## 5. 기동

```bash
docker compose up -d --build
```

첫 빌드는 ARM에서 몇 분 걸린다. 컨테이너가 뜨면 스키마는 자동으로 맞춰진다 —
`Dockerfile`의 시작 명령이 `alembic upgrade head`를 먼저 실행한다.

```bash
docker compose logs -f bot
```

`내전도우미#8506 로그인 완료`가 보이면 성공. Discord에서 `/ping`으로 확인한다.

## 6. 운영

```bash
docker compose ps                      # 상태
docker compose logs -f bot             # 실시간 로그
docker compose logs bot | grep teams_generated   # 구조화 로그 추적
docker compose restart bot             # 재시작
docker compose exec db psql -U war war_helper    # DB 접속
```

**코드 업데이트** — GitHub에 push한 뒤 서버에서:

```bash
git pull && docker compose up -d --build
```

진행 중이던 내전은 재시작 후에도 유지된다. `restore_views()`가 열려 있던 내전의
버튼을 다시 등록한다.

**VM 재부팅** — `restart: unless-stopped`와 `systemctl enable docker` 덕분에
자동으로 다시 뜬다.

**백업** — 내전 기록이 쌓이면:

```bash
docker compose exec db pg_dump -U war war_helper > backup-$(date +%F).sql
```

## 문제가 생기면

| 증상 | 확인 |
|---|---|
| 봇이 크래시 루프 | `docker compose logs bot`. `ValidationError`면 `.env`에 `DISCORD_TOKEN` / `RIOT_API_KEY`가 빠진 것 |
| 슬래시 명령이 안 보임 | `.env`의 `DISCORD_GUILD_ID`에 해당 서버 ID가 있는지, 봇이 그 서버에 초대됐는지 |
| 명령이 두 번 응답 | 로컬이나 다른 곳에서 같은 토큰으로 봇이 켜져 있다 |
| `/등록`만 실패 | Riot 키 만료. 개발용 키는 24시간마다 갱신해야 한다 |
| DB 연결 실패 | `docker compose ps`로 `db`가 healthy인지 확인 |
