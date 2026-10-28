"""Regression tests for completion-before-feedback and terminal state cleanup."""
import server
from server import Player, Room


def room_with_second_set(receiver_bot):
    room=Room(code='P0CASE', humans=1, mission=3, city='new_york', debug=False)
    room.players=[Player(name=f'P{i}',token=str(i),seat=i,char=i,bot=(i==1 and receiver_bot)) for i in range(4)]
    room.phase='turn';room.turn=0
    # First completed set has already been scored; second set is completed
    # by the source now passing its extra non-set card away.
    room.completion_order=[{'player':2,'character':2,'color':'green','position':1}]
    room.players[2].done=True
    room.players[0].hand=['blue-1','blue-2','blue-3','blue-4','blue-5','brown-2']
    room.players[0].chips=3
    room.players[1].hand=['brown-1','brown-3','brown-4','brown-5','magenta-1']
    room.players[1].chips=1
    room.players[3].hand=['magenta-2','magenta-3','magenta-4','magenta-5','start']
    return room


def test_ny03_second_set_success_precedes_ai_last_chip():
    r=room_with_second_set(True)
    server.pass_card(r,0,'brown-2',1)
    assert r.result=='success'
    assert r.phase=='ended'
    assert r.turn is None
    assert r.players[1].chips==1
    assert len(r.completion_order)==2
    assert r.pending is None


def test_ny03_second_set_success_precedes_human_feedback():
    r=room_with_second_set(False)
    server.pass_card(r,0,'brown-2',1)
    assert r.result=='success'
    assert r.phase=='ended'
    assert r.turn is None
    assert r.pending is None
    assert r.players[1].chips==1


def test_completion_order_failure_does_not_restore_turn():
    r=Room(code='FAILCASE', humans=1, mission=1, city='paris', debug=False)
    r.players=[Player(name=f'P{i}',token=str(i),seat=i,char=i,bot=False) for i in range(4)]
    r.phase='turn';r.turn=1
    r.players[1].hand=['blue-1','blue-2','blue-3','blue-4','blue-5','brown-1']
    r.players[1].chips=4
    r.players[0].hand=['green-1','green-2','green-3','green-4','brown-2']
    r.players[0].chips=4
    server.pass_card(r,1,'brown-1',0)
    assert r.result=='failure'
    assert r.phase=='ended'
    assert r.turn is None
    assert r.pending is None
