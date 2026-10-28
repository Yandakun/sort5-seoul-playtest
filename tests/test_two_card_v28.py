import server
from fastapi.testclient import TestClient
from pathlib import Path
C=TestClient(server.APP)

def prepare(city, n):
    server.ROOMS.clear()
    owner=C.post('/api/new',json={'name':'P0','humans':4,'city':city,'mission':n}).json()
    members=[owner]
    for i in range(1,4):
        members.append(C.post('/api/join',json={'name':f'P{i}','code':owner['code']}).json())
    def action(i,typ,**kw):
        return C.post('/api/action',json={'code':owner['code'],'token':members[i]['token'],'type':typ,**kw})
    assert action(0,'begin').status_code==200
    for i in range(4):assert action(i,'character',character=i).status_code==200
    room=server.ROOMS[owner['code']]
    return room,members,action

def test_offer_private_to_recipient_and_other_players():
    r,m,a=prepare('berlin',3)
    r.turn=3
    cards=[c for c in r.players[3].hand if c!='start'][:2]
    assert a(3,'pass',card=cards[0],target=2).status_code==400
    res=a(3,'offer',cards=cards,target=2)
    assert res.status_code==200,res.text
    for member in m:
        view=C.get('/api/state',params={'code':r.code,'token':member['token']}).json()
        assert view['phase']=='offer_choice'
        assert 'cards' not in view['offer']
        assert 'cards' not in (view.get('pending') or {})
        assert view['offer']['public_cards']==[None,None]
    assert a(1,'choose_offer',choice='0').status_code==400
    assert a(2,'choose_offer',choice='0').status_code==200
    assert cards[0] in r.players[2].hand and cards[1] in r.players[3].hand

def test_paris_all_players_must_offer_two():
    r,m,a=prepare('paris',2)
    for i in range(4):
        r.turn=i;r.phase='turn'
        hand=[c for c in r.players[i].hand if c!='start']
        assert a(i,'pass',card=hand[0],target=(i+1)%4).status_code==400
        assert a(i,'offer',cards=hand[:2],target=(i+1)%4).status_code==200
        assert a((i+1)%4,'choose_offer',choice='1').status_code==200
        r.phase='turn'

def test_two_card_frontend_controls_present():
    js=(Path(__file__).parents[1]/'static/app.js').read_text()
    for token in ['secondOfferCard','data-offer-choice','Choose One Card',"action('offer'", "action('choose_offer'"]:
        assert token in js
