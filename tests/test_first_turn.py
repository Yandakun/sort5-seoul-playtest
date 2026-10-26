import pytest
from fastapi.testclient import TestClient
import server

client = TestClient(server.APP)

@pytest.mark.parametrize("mission", [1,2,3,4,5])
@pytest.mark.parametrize("human_char", [1,2,3])
def test_ai_starts_when_human_did_not_choose_triangle(mission, human_char):
    created=client.post("/api/new",json={"name":"Human","humans":1,"mission":mission}).json()
    payload={"code":created["code"],"token":created["token"]}
    def act(kind, **extra):
        r=client.post("/api/action",json={**payload,"type":kind,**extra})
        assert r.status_code==200,r.text
        return r.json()
    act("begin")
    snap=act("character",character=human_char)
    if mission==2:
        my_hand=snap["players"][0]["hand"]
        card=next(c["id"] for c in my_hand if c["id"] and c["id"]!="start")
        snap=act("reveal",card=card)
    assert snap["phase"]=="turn"
    idx=snap["turn"]
    assert idx!=snap["me"]
    assert snap["players"][idx]["char"]==0
    assert snap["players"][idx]["bot"]
    assert snap["ai_waiting"]
    assert snap["starting_player"]==idx
    assert snap["moves"]==0
    advance=act("advance_ai")
    assert advance["moves"]==1

@pytest.mark.parametrize("mission", [1,2,3,4,5])
def test_human_starts_only_if_triangle(mission):
    created=client.post("/api/new",json={"name":"Human","humans":1,"mission":mission}).json()
    payload={"code":created["code"],"token":created["token"]}
    def act(kind, **extra):
        r=client.post("/api/action",json={**payload,"type":kind,**extra})
        assert r.status_code==200,r.text
        return r.json()
    act("begin");snap=act("character",character=0)
    if mission==2:
        card=next(c["id"] for c in snap["players"][0]["hand"] if c["id"] and c["id"]!="start")
        snap=act("reveal",card=card)
    assert snap["turn"]==snap["me"]==0
    assert snap["starting_player"]==0
    assert not snap["ai_waiting"]
