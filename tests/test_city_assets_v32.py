from pathlib import Path
from mission_rules import M, CITY_ORDER
from fastapi.testclient import TestClient
import server

ROOT=Path(__file__).resolve().parents[1]/'static'/'assets'
PREFIX=lambda c: 'newyork' if c=='new_york' else c

def test_every_city_mission_has_both_assets():
    for city in CITY_ORDER:
        for n in range(1,6):
            for side in ('front','back'):
                path=ROOT/f'{PREFIX(city)}_{n:02d}_{side}.png'
                assert path.is_file() and path.stat().st_size>1000, str(path)

def test_all_30_missions_can_create_rooms():
    client=TestClient(server.APP)
    for city in CITY_ORDER:
        for n in range(1,6):
            r=client.post('/api/new',json={'name':'Tester','city':city,'mission':n,'humans':1})
            assert r.status_code==200,(city,n,r.text)
            d=r.json()
            assert d.get('code'), (city,n,d)

def test_mission_registry_matches_api_assets():
    result=TestClient(server.APP).get('/api/missions').json()
    assert len(result['cities'])==6
    for city in result['cities']:
        assert len(city['missions'])==5
        for m in city['missions']:
            assert m['artwork_prefix']==f"{PREFIX(city['id'])}_{m['number']:02d}"
