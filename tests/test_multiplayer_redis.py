"""Integration checks: two independent clients using a simulated shared Redis store.
This verifies server-side persistence, turn ownership, visibility and concurrent-seat setup.
It is not a live Upstash production integration test.
"""
import json
import pytest
from fastapi.testclient import TestClient
import server

@pytest.fixture
def online(monkeypatch):
    kv={}
    def cmd(*args):
        op=args[0].upper()
        if op=='GET': return kv.get(args[1])
        if op=='SET':
            key,val=args[1:3]
            if 'NX' in args[3:] and key in kv:return None
            kv[key]=val
            return 'OK'
        if op=='EVAL':
            key,owner=args[-2:]
            if kv.get(key)==owner:
                kv.pop(key,None)
                return 1
            return 0
        raise AssertionError(f'unexpected redis command {args}')
    monkeypatch.setattr(server,'REMOTE_STORE',True)
    monkeypatch.setattr(server,'redis_command',cmd)
    return TestClient(server.APP),TestClient(server.APP),kv

def req(client,route,payload):
    response=client.post(route,json=payload)
    assert response.status_code==200,response.text
    return response.json()

def act(client,member,kind,**extra):
    return req(client,'/api/action',dict(code=member['code'],token=member['token'],type=kind,**extra))

def view(client,member):
    res=client.get('/api/state',params={'code':member['code'],'token':member['token']})
    assert res.status_code==200,res.text
    return res.json()

def test_online_two_person_room_and_feedback(online):
    c1,c2,kv=online
    host=req(c1,'/api/new',dict(name='Host',humans=2,mission=5,debug=True))
    assert kv['sort5:room:'+host['code']]
    room_state=view(c1,host)
    assert room_state['debug'] is False  # no public private-hand inspection
    second=req(c2,'/api/join',dict(name='Guest',code=host['code']))
    assert second['code']==host['code']
    a=view(c1,host);b=view(c2,second)
    assert a['human_joined']==2 and b['human_joined']==2
    act(c1,host,'begin')
    act(c1,host,'character',character=0)
    act(c2,second,'character',character=1)
    h=view(c1,host);g=view(c2,second)
    assert h['phase']=='turn' and g['phase']=='turn'
    assert h['turn']==g['turn']==0
    assert len(h['players'])==len(g['players'])==4
    card=next(c['id'] for c in h['players'][0]['hand'] if c['id'] and c['id']!='start')
    assert card not in [c['id'] for c in g['players'][0]['hand'] if c['id'] is not None]
    act(c1,host,'pass',card=card,target=1)
    guest_state=view(c2,second)
    host_state=view(c1,host)
    assert guest_state['phase']=='feedback'
    assert guest_state['pending']['card']==card
    assert 'card' not in host_state['pending']
    act(c2,second,'feedback',positive=False)
    assert view(c1,host)['phase'] in ('turn','ended')
    events=view(c1,host)['turn_events']
    assert any(e.get('reaction')=='negative' for e in events)
    assert not any(e.get('card')==card for e in events)  # nonpublic card kept private

def test_online_four_humans_and_duplicate_join(online):
    c1,c2,kv=online
    host=req(c1,'/api/new',dict(name='P0',humans=4,mission=1))
    members=[host]
    for n in range(1,4):
        members.append(req(c2,'/api/join',dict(name=f'P{n}',code=host['code'])))
    res=c2.post('/api/join',json={'name':'P4','code':host['code']})
    assert res.status_code==409
    act(c1,host,'begin')
    for i,m in enumerate(members): act(c1 if i%2==0 else c2,m,'character',character=i)
    all_s=[view(c1 if i%2==0 else c2,m) for i,m in enumerate(members)]
    assert all(s['phase']=='turn' for s in all_s)
    assert all(s['turn']==0 for s in all_s)
    assert all(len(s['players'])==4 for s in all_s)
