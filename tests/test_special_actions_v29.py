import server
from fastapi.testclient import TestClient
from pathlib import Path
client=TestClient(server.APP)

def prepare(city,mission,humans=4):
    server.ROOMS.clear()
    r=client.post('/api/new',json={'name':'P0','city':city,'mission':mission,'humans':humans})
    assert r.status_code==200,r.text
    members=[r.json()];code=r.json()['code']
    for i in range(1,humans):
        j=client.post('/api/join',json={'name':f'P{i}','code':code})
        assert j.status_code==200,j.text
        members.append(j.json())
    def action(i,typ,**kw):
        return client.post('/api/action',json={'code':code,'token':members[i]['token'],'type':typ,**kw})
    assert action(0,'begin').status_code==200
    for i in range(humans): assert action(i,'character',character=i).status_code==200
    return server.ROOMS[code],members,action

def test_newyork_each_human_locks_secret_initial_card():
    room,m,act=prepare('new_york',2)
    assert room.phase=='initial_pass'
    cards=[next(x for x in p.hand if x!='start') for p in room.players]
    assert not room.turn_events
    a=act(0,'initial_pass',card=cards[0]);assert a.status_code==200
    assert a.json()['initial_pass_submitted'] is True
    assert a.json()['initial_pass_ready']==1
    b=client.get('/api/state',params={'code':room.code,'token':m[1]['token']}).json()
    assert b['initial_pass_submitted'] is False
    assert cards[0] not in repr(b['pending'])
    assert all(cards[i] in room.players[i].hand for i in range(4))
    assert act(0,'initial_pass',card=cards[0]).status_code==400
    for i in (1,2,3):assert act(i,'initial_pass',card=cards[i]).status_code==200
    assert room.phase=='turn'
    for i,x in enumerate(cards):assert x in room.players[(i+1)%4].hand
    assert room.move_count==0
    assert room.turn==0

def test_newyork_human_ai_initial_pass_auto_bot_selections():
    room,m,act=prepare('new_york',2,humans=2)
    assert room.phase=='initial_pass'
    assert len(room.initial_passes)==2
    for i in (0,1):
        card=next(x for x in room.players[i].hand if x!='start')
        assert act(i,'initial_pass',card=card).status_code==200
    assert room.phase=='turn'
    assert room.turn==0

def test_london_guess_hidden_and_public_result_and_chip_cost():
    room,m,act=prepare('london',4)
    card=next(x for x in room.players[0].hand if x!='start')
    chips=room.shared_chips
    response=act(0,'pass',card=card,target=1)
    assert response.status_code==200 and response.json()['phase']=='guess'
    b=client.get('/api/state',params={'code':room.code,'token':m[1]['token']}).json()
    assert b['allowed_actions']==['guess_number']
    assert 'card' not in b['pending'] and b['pending']['to']==1
    assert act(2,'guess_number',guess=1).status_code==400
    assert act(1,'guess_number',guess=6).status_code==400
    wrong=2 if server.num(card)==1 else 1
    r=act(1,'guess_number',guess=wrong)
    assert r.status_code==200 and r.json()['phase']=='feedback'
    event=r.json()['turn_events'][-1]
    assert event['guessed_number']==wrong and event['guess_wrong'] is True
    assert 'number' not in event and event['card'] is None
    assert act(1,'feedback',positive=True).status_code==200
    assert room.shared_chips==chips-2

def test_new_ui_widgets_present():
    source=(Path(__file__).parents[1]/'static/app.js').read_text()
    for value in ('initialPassPanel','guessNumberPanel',"action('initial_pass'", "action('guess_number'",'initial_pass_submitted','data-guess'):
        assert value in source
