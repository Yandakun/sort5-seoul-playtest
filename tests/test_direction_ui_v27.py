import server
from fastapi.testclient import TestClient
client=TestClient(server.APP)

def setup_room(city,mission,chars):
    server.ROOMS.clear()
    res=client.post('/api/new',json={'name':'Host','humans':1,'city':city,'mission':mission})
    assert res.status_code==200,res.text
    data=res.json()
    assert client.post('/api/action',json={'code':data['code'],'token':data['token'],'type':'begin'}).status_code==200
    room=server.ROOMS[data['code']]
    room.phase='turn';room.turn=0
    for i,p in enumerate(room.players):
        p.char=chars[i];p.hand=[f'blue{i+1}'];p.done=False
    return room,data

def legal(room,token):return client.get('/api/state',params={'code':room.code,'token':token}).json()['legal_targets']

def test_berlin_left_ui_targets():
    room,data=setup_room('berlin',2,[3,0,1,2])
    assert legal(room,data['token'])==[3]
    room.players[3].done=True
    assert legal(room,data['token'])==[2]
    room.players[2].done=True
    assert legal(room,data['token'])==[1]

def test_tokyo_opposite_prohibited():
    room,data=setup_room('tokyo',1,[0,1,2,3])
    assert set(legal(room,data['token']))=={1,3}

def test_tokyo_right_forbidden_when_three_or_four_active():
    room,data=setup_room('tokyo',5,[0,1,2,3])
    assert set(legal(room,data['token']))=={2,3}
    room.players[1].done=True
    assert set(legal(room,data['token']))=={3}
    room.players[3].done=True
    assert legal(room,data['token'])==[2]

def test_no_legal_targets_outside_human_turn():
    room,data=setup_room('berlin',2,[3,0,1,2]);room.turn=1
    assert legal(room,data['token'])==[]

def test_bot_never_chooses_illegal_recipient():
    room,_=setup_room('berlin',2,[3,0,1,2]);room.turn=0
    room.players[0].bot=True
    for _ in range(15):
        result=server.bot_choice(room,0)
        assert result is not None and result[1]==3
