import asyncio
import json
from lcu_driver import Connector

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

connector = Connector(loop=loop)

@connector.ready
async def connect(connection):
    print("롤 클라이언트 연결 성공!")
    
    # 1. 로그인된 유저 PUUID 조회
    summoner = await connection.request('get', '/lol-summoner/v1/current-summoner')
    summoner_data = await summoner.json()
    puuid = summoner_data['puuid']

    # 2. 최근 매치 목록 조회 (커스텀 게임 탐색용)
    history = await connection.request('get', f'/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=20')
    history_data = await history.json()
    
    games = history_data.get('games', {}).get('games', [])
    
    # 가장 최근 사용자 설정 게임 찾기
    latest_custom_game_id = None
    for game in games:
        if game.get('gameType') == 'CUSTOM_GAME':
            latest_custom_game_id = game.get('gameId')
            break
            
    if not latest_custom_game_id:
        print("최근 20경기 내에 사용자 설정 게임이 없습니다.")
        return

    print(f"가장 최근 커스텀 게임 ID: {latest_custom_game_id}")

    # 3. gameId로 10명 전체 상세 데이터 가져오기
    game_detail_res = await connection.request('get', f'/lol-match-history/v1/games/{latest_custom_game_id}')
    game_detail = await game_detail_res.json()

    # 4. 'custom_matches.json'으로 고정 저장
    with open('custom_matches.json', 'w', encoding='utf-8') as f:
        json.dump(game_detail, f, ensure_ascii=False, indent=4)
        
    print("10명 플레이어 상세 데이터 저장 완료: 'custom_matches.json'")

@connector.close
async def disconnect(connection):
    print("클라이언트 연결 종료")

if __name__ == '__main__':
    connector.start()