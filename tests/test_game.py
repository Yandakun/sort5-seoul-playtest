from collections import Counter
import pytest
from fastapi.testclient import TestClient
import server

client = TestClient(server.APP)

def room(humans=1, mission=1, debug=False):
    r=client.post('/api/new',json={'name':'P0','humans':humans,'mission':mission,'debug':debug})
    assert r.status_code==200
    creator=r.json();members=[creator]
    for i in range(1,humans):
        resp=client.post('/api/join',json={'name':f'P{i}','code':creator['code']})
        assert resp.status_code==200
        members.append(resp.json())
    return creator['code'],members

def action(code, member, act, **kw):
    r=client.post('/api/action',json={'code':code,'token':member['token'],'type':act,**kw})
    assert r.status_code==200, r.text
    return r.json()

def state(code, member, **kw):
    r=client.get('/api/state',params={'code':code,'token':member['token'],**kw})
    assert r.status_code==200
    return r.json()

@pytest.mark.parametrize('mission,expected',[ (1,[6,6,6,6]),(2,[5,5,5,5]),(3,[5,4,5,5]),(4,[6,6,4,5]),(5,[6,6,6,6]) ])
def test_setup_5_missions(mission,expected):
    code,members=room(4,mission)
    s=action(code,members[0],'begin')
    assert s['phase']=='characters'
    if mission==3:
        assert len(server.ROOMS[code].public)==4
    for i,member in enumerate(members):
        s=action(code,member,'character',character=i)
    assert sorted(p['char'] for p in s['players'])==[0,1,2,3]
    assert [p['chips'] for p in s['players']]==expected
    if mission==2:
        assert s['phase']=='reveal'
        for member in members:
            ss=state(code,member)
            hand=ss['players'][ss['me']]['hand']
            chosen=next(c['id'] for c in hand if c['id']!='start')
            s=action(code,member,'reveal',card=chosen)
        assert len(server.ROOMS[code].public)==4
    assert s['phase']=='turn'
    assert s['turn']==0
    assert s['players'][0]['hand_size']==6
    assert [x['id'] for x in state(code,members[0])['players'][0]['hand']].count('start')==1
    assert sum(p['hand_size'] for p in s['players'])==21

def test_start_card_relay_completes_all_sets():
    code,members=room(4,1)
    action(code,members[0],'begin')
    for i,member in enumerate(members):s=action(code,member,'character',character=i)
    r=server.ROOMS[code]
    with r.lock:
        for i,color in enumerate(server.COLORS):
            r.players[i].hand=[f'{color}-{j}' for j in range(1,6)]
        r.players[0].hand.append('start')
        r.turn=0
    s=action(code,members[0],'pass',card='start',target=1)
    assert s['players'][0]['done']
    assert s['turn']==1
    assert s['players'][1]['chips']==5 # start costs a negative chip (provisional interpretation)
    s=action(code,members[1],'pass',card='start',target=2)
    assert s['players'][1]['done']
    s=action(code,members[2],'pass',card='start',target=3)
    assert s['phase']=='ended'
    assert s['result']=='success'
    assert all(p['done'] for p in s['players'])

def test_hidden_card_privacy_and_faceup_rules():
    for mission in [1,4,5]:
        code,members=room(4,mission)
        action(code,members[0],'begin')
        for i,member in enumerate(members):s=action(code,member,'character',character=i)
        p0=state(code,members[0])
        p1=state(code,members[1])
        assert all(c['id'] is None for c in p1['players'][0]['hand'] if not c['public'])
        my_card=next(c['id'] for c in p0['players'][0]['hand'] if c['id']!='start')
        s=action(code,members[0],'pass',card=my_card,target=1)
        p2=state(code,members[2])
        receiver=state(code,members[1])
        transferred=next(c for c in receiver['players'][1]['hand'] if c['id']==my_card)
        assert transferred['visible']
        assert transferred['public']==(mission==1)
        if mission==1:
            assert my_card in [c['id'] for c in p2['players'][1]['hand']]
        else:
            assert my_card not in [c['id'] for c in p2['players'][1]['hand']]

def test_mission_2_revealed_cards_stay_public_after_transfer():
    code,members=room(4,2)
    action(code,members[0],'begin')
    for i,member in enumerate(members):action(code,member,'character',character=i)
    chosen=[]
    for member in members:
        st=state(code,member)
        card=next(c['id'] for c in st['players'][st['me']]['hand'] if c['id']!='start')
        chosen.append(card)
        action(code,member,'reveal',card=card)
    s=action(code,members[0],'pass',card=chosen[0],target=1)
    observer=state(code,members[2])
    assert chosen[0] in [x['id'] for x in observer['players'][1]['hand']]
    assert s['phase']=='feedback'
    assert s['pending'].get('card') is None # only recipient sees specific received card
    recipient=state(code,members[1])
    assert recipient['pending']['card']==chosen[0]

def test_debug_inspection_restricted(monkeypatch):
    monkeypatch.setenv("SORT5_ALLOW_DEBUG", "true")
    code,members=room(2,1,debug=True)
    action(code,members[0],'begin')
    resp=client.get('/api/state',params={'code':code,'token':members[1]['token'],'inspect':0})
    assert resp.status_code==403
    resp=client.get('/api/state',params={'code':code,'token':members[0]['token'],'inspect':1})
    assert resp.status_code==200

def test_human_cannot_play_bot_cards():
    code,members=room(1,1)
    action(code,members[0],'begin')
    action(code,members[0],'character',character=0)
    req=client.post('/api/action',json={'code':code,'token':members[0]['token'],'type':'pass','card':'not-a-card','target':1})
    assert req.status_code==400

def test_mission_4_circle_character_faceup_transfer():
    code,members=room(4,4)
    action(code,members[0],'begin')
    for i,member in enumerate(members): action(code,member,'character',character=i)
    r=server.ROOMS[code]
    with r.lock: r.turn=1
    send_card=next(c for c in r.players[1].hand if c!='start')
    action(code,members[1],'pass',card=send_card,target=2)
    p3=state(code,members[3])
    assert send_card in [c['id'] for c in p3['players'][2]['hand']]
    assert send_card in r.public

def test_feedback_decrements_and_is_not_hidden_from_log():
    code,members=room(4,5)
    action(code,members[0],'begin')
    for i,member in enumerate(members):action(code,member,'character',character=i)
    r=server.ROOMS[code]
    send_card=next(c for c in r.players[0].hand if c!='start')
    action(code,members[0],'pass',card=send_card,target=1)
    before=state(code,members[1])['players'][1]['chips']
    s=action(code,members[1],'feedback',positive=True)
    assert s['players'][1]['chips']==before-1
    assert any('green / needed' in e['text'] for e in s['history'])

def test_success_allows_mission_advance():
    code,members=room(4,1)
    action(code,members[0],'begin')
    for i,member in enumerate(members):action(code,member,'character',character=i)
    r=server.ROOMS[code]
    with r.lock:
        for i,color in enumerate(server.COLORS):r.players[i].hand=[f'{color}-{n}' for n in range(1,6)]
        r.players[0].hand.append('start')
    for i in range(3):action(code,members[i],'pass',card='start',target=i+1)
    s=action(code,members[0],'next')
    assert s['phase']=='lobby' and s['mission']==2
    assert s['players'][0]['hand_size']==0

def test_ai_turn_requires_click_and_records_visual_feedback():
    code, members = room(1, 1)
    action(code,members[0],'begin')
    s=action(code,members[0],'character',character=1)
    # Force an AI player to be the Starting Card holder and first actor.
    r=server.ROOMS[code]
    with r.lock:
        i=next(j for j,p in enumerate(r.players) if p.char==0)
        assert r.players[i].bot
        assert r.turn==i
        assert r.move_count==0
    s=state(code,members[0])
    assert s['ai_waiting'] and s['moves']==0
    s=action(code,members[0],'advance_ai')
    assert s['moves']==1
    assert len(s['turn_events'])==1
    e=s['turn_events'][0]
    assert e['from']==i and e['to']!=i
    if s['players'][e['to']]['bot']:
        assert e['reaction'] in ('positive','negative')
    else:
        assert e['reaction'] is None and s['phase']=='feedback'
    assert s['moves']==1, 'AI must never chain extra turns automatically'


def test_hidden_turn_history_never_reveals_face_down_card():
    code, members=room(4,5)
    action(code,members[0],'begin')
    for j,m in enumerate(members): action(code,m,'character',character=j)
    ss=state(code,members[0]);card=next(c['id'] for c in ss['players'][0]['hand'] if c['id']!='start')
    s=action(code,members[0],'pass',card=card,target=1)
    e=s['turn_events'][-1]
    assert e['face_up'] is False and e['card'] is None
    assert e['reaction'] is None
    s=action(code,members[1],'feedback',positive=True)
    assert s['turn_events'][-1]['reaction']=='positive'
    assert s['turn_events'][-1]['card'] is None
