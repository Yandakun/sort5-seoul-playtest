import server
from fastapi.testclient import TestClient

client=TestClient(server.APP)

def create_room(humans=4):
    server.ROOMS.clear()
    host=client.post('/api/new',json={'name':'Host','humans':humans,'city':'tokyo','mission':1}).json()
    players=[host]
    for n in range(1,humans):
        response=client.post('/api/join',json={'name':f'Guest{n}','code':host['code']})
        assert response.status_code==200
        players.append(response.json())
    room=server.ROOMS[host['code']]
    return room,players

def test_lobby_seats_are_stable_and_independent_of_character():
    room,people=create_room()
    assert [p.seat for p in room.players]==[0,1,2,3]
    assert server.relative_seat(room,0,'left')==3
    assert server.relative_seat(room,0,'right')==1
    assert server.relative_seat(room,0,'opposite')==2
    assert server.relative_seat(room,2,'left')==1
    assert server.relative_seat(room,2,'right')==3
    assert server.relative_seat(room,2,'opposite')==0
    data=server.snapshot(room,0)
    assert [p['seat'] for p in data['players']]==[0,1,2,3]
    assert [p['seat'] for p in server.snapshot(room,2)['players']]==[0,1,2,3]

def test_seats_survive_character_selection_completion_and_serialization():
    room,people=create_room(2)
    token=people[0]['token'];code=room.code
    begin=client.post('/api/action',json={'code':code,'token':token,'type':'begin'})
    assert begin.status_code==200,begin.text
    assert [p.seat for p in room.players]==[0,1,2,3]
    room.players[1].char=3
    room.players[2].char=0
    room.players[1].done=True
    assert server.relative_seat(room,0,'right')==1
    assert server.relative_seat(room,0,'left')==3
    recovered=server.room_from_json(server.room_to_json(room))
    assert [p.seat for p in recovered.players]==[0,1,2,3]
    assert server.relative_seat(recovered,2,'opposite')==0

def test_legacy_room_without_seat_uses_existing_index_order():
    room,_=create_room()
    for p in room.players:p.seat=None
    assert server.relative_seat(room,0,'left')==3
    assert server.relative_seat(room,0,'right')==1

def test_snapshot_seat_is_not_secret():
    room,people=create_room()
    for i,auth in enumerate(people):
        response=client.get('/api/state',params={'code':room.code,'token':auth['token']})
        assert response.status_code==200
        assert [p['seat'] for p in response.json()['players']]==[0,1,2,3]


def test_left_only_skips_completed_seat_but_keeps_physical_positions():
    room,_=create_room()
    room.city='berlin';room.mission=2
    room.phase='turn';room.turn=0
    for j,p in enumerate(room.players): p.char=j; p.hand=[f'blue{j+1}']
    # Berlin 02: star player must pass left. Set player 0 as star.
    room.players[0].char=3
    room.players[3].done=True
    assert server.relative_seat(room,0,'left')==3
    assert server.relative_seat(room,0,'left',skip_done=True)==2
    assert server.can_pass(room,0,'blue1',2)
    assert not server.can_pass(room,0,'blue1',1)
    assert [p.seat for p in room.players]==[0,1,2,3]


def test_right_direction_skips_multiple_completed_players():
    room,_=create_room()
    room.players[1].done=True
    assert server.relative_seat(room,0,'right',skip_done=True)==2
    room.players[2].done=True
    assert server.relative_seat(room,0,'right',skip_done=True)==3
    room.players[3].done=True
    assert server.relative_seat(room,0,'right',skip_done=True)==-1
    assert server.relative_seat(room,0,'opposite')==2


def test_left_wraps_after_completed_neighbors():
    room,_=create_room()
    room.players[3].done=True
    room.players[2].done=True
    assert server.relative_seat(room,0,'left',skip_done=True)==1
