@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

REM ===================================================================
REM  내전 전적 추출기
REM
REM  롤 클라이언트가 켜져 있는 동안 열리는 로컬 API(LCU)에서 사설 게임
REM  목록을 보여주고, 고른 경기를 custom_matches.json 으로 저장한다.
REM  이 파일을 디스코드 /결과 의 전적파일 칸에 첨부하면 개인 성적까지 남는다.
REM
REM  Python 도 추가 설치도 필요 없다. 윈도우 10 이상이면 더블클릭.
REM  롤 클라이언트를 켜 둔 채로 실행해야 한다.
REM ===================================================================

echo.
echo   내전 전적 추출기
echo   ========================================

REM --- 1. 접속 정보 얻기 ------------------------------------------------
REM  lockfile 경로를 추측하지 않는다. 설치 드라이브가 제각각이고 클라이언트가
REM  파일을 잠그기도 한다. 대신 실행 중인 프로세스의 명령줄에서 읽는다.
REM  LeagueClientUx.exe 는 --app-port 와 --remoting-auth-token 을 달고 뜬다.
echo   클라이언트를 찾는 중...

set "PS=$ErrorActionPreference='SilentlyContinue';"
set "PS=!PS! $all = @(Get-CimInstance Win32_Process);"
set "PS=!PS! $p = $all.Where({$_.Name -eq 'LeagueClientUx.exe' -or $_.Name -eq 'LeagueClient.exe'});"
set "PS=!PS! foreach ($x in $p) {"
set "PS=!PS!   $cl = [string]$x.CommandLine;"
set "PS=!PS!   $a = [regex]::Match($cl, '--app-port=(\d+)');"
set "PS=!PS!   $b = [regex]::Match($cl, '--remoting-auth-token=([\w\-_]+)');"
set "PS=!PS!   if ($a.Success -and $b.Success) { $a.Groups[1].Value + '|' + $b.Groups[1].Value; break }"
set "PS=!PS! }"

set "PORT="
set "PASS="
for /f "usebackq tokens=1,2 delims=|" %%a in (`powershell -NoProfile -Command "!PS!"`) do (
  set "PORT=%%a"
  set "PASS=%%b"
)

if not defined PORT goto :noclient
if not defined PASS goto :noclient

echo   연결 포트: !PORT!

set "API=https://127.0.0.1:!PORT!"
set "TMPJSON=%TEMP%\lol_match_list.json"
set "OUT=%~dp0custom_matches.json"

REM --- 2. 최근 20경기 목록 받기 ---------------------------------------
REM  자체 서명 인증서라 -k 가 필요하다. 아이디는 riot 고정.
echo   최근 경기를 불러오는 중...
curl -s -k -u "riot:!PASS!" -o "!TMPJSON!" "!API!/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=20"

if errorlevel 1 (
  echo   [실패] 클라이언트에 연결하지 못했습니다.
  echo          로그인까지 마친 상태인지 확인해주세요.
  goto :fail
)

REM --- 3. 사설 게임 목록 뽑기 ------------------------------------------
REM  PowerShell 안에서 파이프와 큰따옴표를 쓰지 않는다. 배치가 먼저 먹어버린다.
REM  한 줄에 'gameId|날짜 시각|길이' 형태로 내보낸다.
set "LS=$ErrorActionPreference='SilentlyContinue';"
set "LS=!LS! $j = ConvertFrom-Json (Get-Content -Raw -Encoding UTF8 '!TMPJSON!');"
set "LS=!LS! $c = @($j.games.games).Where({$_.gameType -eq 'CUSTOM_GAME'});"
set "LS=!LS! foreach ($g in $c) {"
set "LS=!LS!   $t = [datetime]$g.gameCreationDate;"
set "LS=!LS!   $m = [int]($g.gameDuration / 60);"
set "LS=!LS!   $note = '';"
set "LS=!LS!   if ([string]$g.endOfGameResult -like 'Abort*') { $note = ' [중단됨]' };"
set "LS=!LS!   [string]$g.gameId + '|' + $t.ToLocalTime().ToString('MM/dd HH:mm') + '|' + [string]$m + '분' + $note"
set "LS=!LS! }"

set "COUNT=0"
echo.
echo   사설 게임 목록
echo   ----------------------------------------
for /f "usebackq tokens=1,2,3 delims=|" %%a in (`powershell -NoProfile -Command "!LS!"`) do (
  set /a COUNT+=1
  set "GID_!COUNT!=%%a"
  echo     !COUNT!^) %%b  ^(%%c^)
)

if "!COUNT!"=="0" (
  echo   [실패] 최근 20경기 안에 사설 게임이 없습니다.
  echo          내전을 뛴 계정으로 로그인했는지 확인해주세요.
  goto :fail
)

REM --- 4. 고르기 --------------------------------------------------------
echo   ----------------------------------------
echo.
set "CHOICE="
set /p "CHOICE=  받을 경기 번호 (그냥 Enter 면 1번): "
if not defined CHOICE set "CHOICE=1"

REM  숫자가 아니거나 범위를 벗어나면 GID_ 조회가 비어서 걸린다.
set "GAMEID=!GID_%CHOICE%!"
if not defined GAMEID (
  echo.
  echo   [실패] 1 부터 !COUNT! 사이의 번호를 골라주세요.
  goto :fail
)

echo.
echo   선택: !CHOICE!번 ^(경기 !GAMEID!^)

REM --- 5. 그 경기의 10명 상세 기록 받기 --------------------------------
REM  목록 응답에는 본인 기록만 들어 있는 판이 있어 경기 상세로 다시 받는다.
REM  curl 이 바이트를 그대로 쓰므로 BOM 이 붙지 않는다. BOM 이 붙으면 봇이 못 읽는다.
echo   10명 상세 기록을 받는 중...
curl -s -k -u "riot:!PASS!" -o "!OUT!" "!API!/lol-match-history/v1/games/!GAMEID!"

if errorlevel 1 (
  echo   [실패] 경기 상세를 받지 못했습니다.
  goto :fail
)

REM --- 6. 제대로 받았는지 확인 -----------------------------------------
REM  인증이 틀리면 오류 본문이 그대로 저장된다. 여기서 안 걸르면 봇에서야 안다.
set "CHK=$ErrorActionPreference='SilentlyContinue';"
set "CHK=!CHK! $g = ConvertFrom-Json (Get-Content -Raw -Encoding UTF8 '!OUT!');"
set "CHK=!CHK! $ids = @($g.participantIdentities);"
set "CHK=!CHK! $named = @($ids.Where({$_.player.gameName}));"
set "CHK=!CHK! [string]$ids.Count + '/' + [string]$named.Count"

set "CHECK="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "!CHK!"`) do set "CHECK=%%i"

set "TOTAL="
set "NAMED="
for /f "tokens=1,2 delims=/" %%a in ("!CHECK!") do (
  set "TOTAL=%%a"
  set "NAMED=%%b"
)

if not defined TOTAL goto :notjson
if "!TOTAL!"=="0" goto :notjson

echo.
echo   ========================================
echo   저장 완료: custom_matches.json
echo   참가자 !TOTAL!명 ^(이름 확인 !NAMED!명^)
echo.
echo   디스코드에서 /결과 의 전적파일 칸에 첨부해주세요.

if not "!TOTAL!"=="10" (
  echo.
  echo   [주의] 참가자가 10명이 아닙니다. 다른 경기를 받았을 수 있습니다.
)

del "!TMPJSON!" >nul 2>&1
echo.
pause
exit /b 0

:noclient
echo   [실패] 롤 클라이언트를 찾지 못했습니다.
echo.
echo   - 클라이언트를 켜고 로그인까지 마친 뒤 실행해주세요.
echo   - 게임 중이어도 클라이언트는 떠 있어야 합니다.
goto :fail

:notjson
echo   [실패] 받은 내용이 경기 기록이 아닙니다.
echo          클라이언트를 껐다 켠 뒤 다시 실행해주세요.

:fail
echo.
pause
exit /b 1
