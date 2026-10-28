import pytest
import server
from mission_rules import M
from fastapi.testclient import TestClient
C=TestClient(server.APP)

def launch(city,n,humans=4):
    server.ROOMS.clear()
    a=C.post('/api/new',json={'name':'Tester0','humans':humans,'city':city,'mission':n});assert a.status_code==200,a.text
    tok=[a.json()];code=tok[0]['code']
    for i in range(1,humans):
        r=C.post('/api/join',json={'name':f'Tester{i}','code':code});assert r.status_code==200,r.text;tok.append(r.json())
    def act(i,kind,**kwargs):
        r=C.post('/api/action',json={'code':code,'token':tok[i]['token'],'type':kind,**kwargs})
        assert r.status_code==200,r.text
        return r.json()
    act(0,'begin')
    for i in range(humans):s=act(i,'character',character=i)
    return server.ROOMS[code],tok,act,s

def test_registry_has_30_and_enforced_city_name():
    assert len(M)==30
    assert C.post('/api/new',json={'name':'x','mission':6,'city':'berlin'}).status_code==422
    assert C.post('/api/new',json={'name':'x','mission':1,'city':'mars'}).status_code==422

@pytest.mark.parametrize('city,n',list(M))
def test_all_mission_configuration_initializes(city,n):
    r,t,act,s=launch(city,n)
    cfg=M[(city,n)]
    assert s['city']==city
    if cfg.pool is not None: assert r.shared_chips==cfg.pool
    else: assert [p.chips for p in r.players]==list(cfg.chips)
    if cfg.held_player is not None:
        holder=next(p for p in r.players if p.char==cfg.held_player)
        assert holder.held_card is not None
    assert s['phase'] in {'turn','reveal','initial_pass'}

def test_berlin_left_only_direction():
    r,t,act,s=launch('berlin',2)
    c=next(c for c in r.players[3].hand if c!='start')
    r.turn=3
    assert server.can_pass(r,3,c,2)
    assert not server.can_pass(r,3,c,0)

def test_tokyo_no_opposite():
    r,t,act,s=launch('tokyo',1)
    c=next(c for c in r.players[0].hand if c!='start')
    assert not server.can_pass(r,0,c,2)
    assert server.can_pass(r,0,c,1)

def test_london_even_number_costs_two_shared_chips():
    r,t,act,s=launch('london',2)
    r.players[0].hand=['brown-2','start','green-1','blue-2','blue-3','green-4']
    n=r.shared_chips
    ss=act(0,'pass',card='brown-2',target=1)
    assert ss['phase']=='feedback'
    act(1,'feedback',positive=True)
    assert r.shared_chips==n-2

def test_two_card_offer_choice_only_one_moves():
    r,t,act,s=launch('berlin',3)
    r.turn=3
    two=[c for c in r.players[3].hand if c!='start'][:2]
    first=len(r.players[3].hand);other=len(r.players[2].hand)
    s=act(3,'offer',cards=two,target=2)
    assert s['phase']=='offer_choice'
    assert s['pending']['public_cards']==[None,None]
    other_view=C.get('/api/state',params={'code':r.code,'token':t[1]['token']}).json()
    assert 'cards' not in other_view.get('pending',{})
    ss=act(2,'choose_offer',choice='1')
    assert len(r.players[3].hand)==first-1 and len(r.players[2].hand)==other+1
    assert two[0] in r.players[3].hand and two[1] in r.players[2].hand

def test_new_york_initial_pass_commit_is_simultaneous():
    r,t,act,s=launch('new_york',2)
    assert s['phase']=='initial_pass'
    before=[next(c for c in p.hand if c!='start') for p in r.players]
    for i,c in enumerate(before):
        act(i,'initial_pass',card=c)
    assert r.phase=='turn'
    for i,c in enumerate(before): assert c in r.players[(i+1)%4].hand

def test_london_guess_does_not_reveal_before_guess():
    r,t,act,s=launch('london',4)
    card=next(c for c in r.players[0].hand if c!='start')
    s=act(0,'pass',card=card,target=1)
    assert s['phase']=='guess'
    view=C.get('/api/state',params={'code':r.code,'token':t[1]['token']}).json()
    assert 'card' not in view['pending']
    assert card not in r.players[1].hand
    chips=r.shared_chips
    wrong=1 if server.num(card)!=1 else 2
    s=act(1,'guess_number',guess=wrong)
    assert card in r.players[1].hand
    assert s['phase']=='feedback'
    act(1,'feedback',positive=True)
    assert r.shared_chips==chips-2

def test_completion_order_failure():
    r,t,act,s=launch('paris',1)
    # Player 0 triangle must complete first. Force circle's ready set and start passing.
    r.players[1].hand=['brown-'+str(n) for n in range(1,6)]
    server.complete_player(r,1)
    assert r.result=='failure'

def test_hidden_number_never_leaks_through_events():
    r,t,act,s=launch('london',2)
    card=next(c for c in r.players[0].hand if c!='start')
    s=act(0,'pass',card=card,target=1)
    recipient=C.get('/api/state',params={'code':r.code,'token':t[1]['token']}).json()
    assert all('number' not in event for event in recipient['turn_events'])
    outsider=C.get('/api/state',params={'code':r.code,'token':t[2]['token']}).json()
    assert all('number' not in event for event in outsider['turn_events'])

def test_ai_respects_pass_direction():
    r,t,act,s=launch('tokyo',1,humans=1)
    # Change turn to AI, then inspect its chosen target.
    r.turn=1
    choice=server.bot_choice(r,1)
    assert choice is not None
    c,target=choice
    assert server.can_pass(r,1,c,target)

def test_public_mission_listing():
    d=C.get('/api/missions').json()
    assert len(d['cities'])==6
    assert sum(len(city['missions']) for city in d['cities'])==30

def test_berlin_count_feedback_is_not_green_or_red_signaling():
    r,t,act,s=launch('berlin',5)
    card=next(c for c in r.players[0].hand if c!='start')
    result=act(0,'pass',card=card,target=1)
    assert result['phase'] == 'turn'
    assert result['turn_events'][-1]['reaction']=='negative'
    assert isinstance(result['turn_events'][-1]['announced_count'],int)

def test_redis_room_serialization_new_fields():
    r,t,act,s=launch('paris',3)
    text=server.room_to_json(r)
    new=server.room_from_json(text)
    assert new.city=='paris' and new.mission==3
    assert new.shared_chips==19
    assert new.players[0].held_card is not None
