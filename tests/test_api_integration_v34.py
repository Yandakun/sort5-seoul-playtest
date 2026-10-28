"""Full JSON HTTP workflow through FastAPI (not a visual-browser test).

One human and three server bots, per mission. Exercises public UI contract:
/api/new, /api/action, /api/state and all special interaction phases.
"""
import random
import pytest
from fastapi.testclient import TestClient
import server
from mission_rules import M

C=TestClient(server.APP)

@pytest.mark.parametrize('city,mission', list(M))
def test_complete_http_session_from_room_to_result(city,mission):
    rng=random.Random(f'ui-contract-{city}-{mission}')
    server.ROOMS.clear()
    created=C.post('/api/new',json={'name':'Human','humans':1,'city':city,'mission':mission})
    assert created.status_code==200,created.text
    auth=created.json()
    def act(kind,**kwargs):
        return C.post('/api/action',json={'code':auth['code'],'token':auth['token'],'type':kind,**kwargs})
    def view():
        res=C.get('/api/state',params=auth)
        assert res.status_code==200,res.text
        return res.json()
    initial=view()
    assert initial['phase']=='lobby' and initial['city']==city and initial['mission']==mission
    assert act('begin').status_code==200
    assert act('character',character=0).status_code==200
    encountered=set()
    for step in range(200):
        s=view();phase=s['phase']; encountered.add(phase)
        assert len(s['players'])==4
        assert sum('start' == c['id'] for c in s['players'][s['me']]['hand']) <= 1
        if phase=='ended':
            assert s['result'] in ('success','failure')
            break
        if phase=='reveal':
            if not s['players'][0]['revealed']:
                card=next(c['id'] for c in s['players'][0]['hand'] if c['id'] and c['id']!='start')
                res=act('reveal',card=card)
            else:
                raise AssertionError('Human already revealed but game still waits in reveal')
        elif phase=='initial_pass':
            if not s['initial_pass_submitted']:
                card=next(c['id'] for c in s['players'][0]['hand'] if c['id'] and c['id']!='start')
                res=act('initial_pass',card=card)
            else:
                raise AssertionError('Game stalled after human submitted the setup card')
        elif phase=='offer_choice':
            assert s['offer'] is not None
            assert s['offer']['to']==0
            res=act('choose_offer',choice=str(rng.randrange(2)))
        elif phase=='guess':
            assert s['pending']['to']==0
            assert 'card' not in s['pending']
            res=act('guess_number',guess=rng.randint(1,5))
        elif phase=='feedback':
            assert s['pending']['to']==0
            res=act('feedback',positive=bool(rng.randint(0,1)))
        elif phase=='turn':
            if s['ai_waiting']:
                res=act('advance_ai')
            else:
                assert s['turn']==0
                room=server.ROOMS[auth['code']]
                options=[(c,j) for c in room.players[0].hand for j in range(1,4) if server.can_pass(room,0,c,j)]
                if not options:
                    # A human unable to make any permitted move is an explicit
                    # impossible situation for this game's mission/rules.
                    raise AssertionError(f'No legal transfer in {city} {mission} at move {s["moves"]}')
                card,target=rng.choice(options)
                if 'offer' in s['allowed_actions']:
                    second=next((x for x in room.players[0].hand if x!=card and server.can_pass(room,0,x,target)),None)
                    if second is None:
                        raise AssertionError(f'No legal two-card offer at {city} {mission}')
                    res=act('offer',cards=[card,second],target=target)
                else:
                    res=act('pass',card=card,target=target)
        else:
            raise AssertionError(f'Unexpected phase {phase}: {city}/{mission}')
        assert res.status_code==200,(city,mission,phase,res.text)
        for viewer in range(4):
            private=server.snapshot(server.ROOMS[auth['code']],viewer)
            for other in range(4):
                if viewer==other:continue
                for item in private['players'][other]['hand']:
                    if item['id'] is not None:
                        assert item['public']
    else:
        raise AssertionError(f'Stuck after 200 steps {city} {mission} {encountered}')
    assert 'turn' in encountered

@pytest.mark.parametrize('city,mission', [('seoul',1),('berlin',3),('new_york',2),('london',4),('paris',2)])
def test_four_human_clients_share_state_and_only_see_own_cards(city,mission):
    server.ROOMS.clear()
    owner=C.post('/api/new',json={'name':'P0','humans':4,'city':city,'mission':mission}).json()
    members=[owner]
    for i in range(1,4):
        response=C.post('/api/join',json={'name':f'P{i}','code':owner['code']})
        assert response.status_code==200,response.text
        members.append(response.json())
    def act(i,kind,**kwargs):
        return C.post('/api/action',json={'code':owner['code'],'token':members[i]['token'],'type':kind,**kwargs})
    def state(i):
        response=C.get('/api/state',params={'code':owner['code'],'token':members[i]['token']})
        assert response.status_code==200,response.text
        return response.json()
    assert act(0,'begin').status_code==200
    for i in range(4):
        assert act(i,'character',character=i).status_code==200
    room=server.ROOMS[owner['code']]
    if room.phase=='initial_pass':
        selected=[]
        for i in range(4):
            card=next(c['id'] for c in state(i)['players'][i]['hand'] if c['id'] not in (None,'start'))
            selected.append(card)
            assert act(i,'initial_pass',card=card).status_code==200
            for j in range(4):
                assert state(j)['phase'] in ('initial_pass','turn')
        for i,card in enumerate(selected):
            assert card in room.players[(i+1)%4].hand
    assert room.phase=='turn'
    # The ▲ seat goes first and is the host for this test.
    assert room.turn==0
    first=next(c['id'] for c in state(0)['players'][0]['hand'] if c['id'] not in (None,'start'))
    if room.players[0].char in server.rule(room).two_cards:
        second=next(c['id'] for c in state(0)['players'][0]['hand'] if c['id'] not in (None,'start',first))
        response=act(0,'offer',cards=[first,second],target=1)
        assert response.status_code==200,response.text
        assert state(1)['phase']=='offer_choice'
        assert state(1)['offer']['public_cards']==[None,None]
        assert act(1,'choose_offer',choice='0').status_code==200
    else:
        response=act(0,'pass',card=first,target=1)
        assert response.status_code==200,response.text
    if room.phase=='guess':
        assert state(1)['pending']['to']==1
        assert 'card' not in state(1)['pending']
        assert act(1,'guess_number',guess=1).status_code==200
    if room.phase=='feedback':
        assert state(1)['pending']['to']==1
        assert act(1,'feedback',positive=True).status_code==200
    for i in range(4):
        s=state(i)
        assert s['moves']==1 and s['players'][i]['is_me']
        assert s['turn']==1 or s['phase']=='ended'
        for j in range(4):
            if i==j:continue
            for entry in s['players'][j]['hand']:
                if entry['id'] is not None: assert entry['public']
