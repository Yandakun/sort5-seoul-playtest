import random
from fastapi.testclient import TestClient
import server
from mission_rules import M
C=TestClient(server.APP)

def begin(city,mission):
    server.ROOMS.clear()
    r=C.post('/api/new',json={'name':'A','humans':2,'city':city,'mission':mission})
    assert r.status_code==200,r.text
    a=r.json(); b=C.post('/api/join',json={'name':'B','code':a['code']}).json()
    def action(player,typ,**kw):
        x=C.post('/api/action',json={'code':a['code'],'token':(a,b)[player]['token'],'type':typ,**kw})
        assert x.status_code==200,x.text
        return x.json()
    action(0,'begin')
    return server.ROOMS[a['code']],(a,b),action

def test_new_york_preparation_does_not_spend_chips():
    r,t,act=begin('new_york',2)
    act(0,'character',character=0)
    s=act(1,'character',character=1)
    assert s['phase']=='initial_pass'
    chips=[p.chips for p in r.players]
    picked=[next(c for c in p.hand if c!='start') for p in r.players]
    for i in (0,1):act(i,'initial_pass',card=picked[i])
    assert r.phase=='turn'
    assert [p.chips for p in r.players]==chips
    assert not r.turn_events

import pytest
@pytest.mark.parametrize('city',["london","paris"])
def test_blind_held_card_selection_and_return(city):
    r,t,act=begin(city,3)
    assert r.phase=='characters'
    assert all(len(p.hand)==0 for p in r.players)
    for token in t:
        view=C.get('/api/state',params={'code':r.code,'token':token['token']}).json()
        assert all(x['hand_size']==0 for x in view['players'])
    act(0,'character',character=2)
    s=act(1,'character',character=0)
    tri=next(p for p in r.players if p.char==0)
    assert tri.held_card is not None
    sealed=tri.held_card
    assert sealed not in tri.hand and len(tri.hand)==5  # Starting Card plus 4
    assert len({c for p in r.players for c in p.hand if c!='start'}|{sealed})==20
    for token in t:
        view=C.get('/api/state',params={'code':r.code,'token':token['token']}).json()
        assert sealed not in str(view)
        ix=next(i for i,p in enumerate(r.players) if p.char==0)
        assert view['players'][ix]['held_face_down'] is True
    # Trigger first set completion through engine; blind card is returned to ▲.
    j=next(i for i,p in enumerate(r.players) if p.char!=0)
    server.complete_player(r,j)
    assert tri.held_card is None
    assert sealed in tri.hand
    assert r.phase!='ended' or r.result!='failure'
    s=C.get('/api/state',params={'code':r.code,'token':t[1]['token']}).json()
    assert not s['players'][ix]['held_face_down']

def test_normal_mission_still_deals_before_character_selection():
    r,t,act=begin('seoul',1)
    assert all(len(p.hand)==5 for p in r.players)
