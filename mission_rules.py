"""SORT5 30-mission rule registry, derived from supplied MissionCards.xlsx.
Symbols: triangle=0, circle=1, square=2, star=3.
The card text is authoritative; interpretations that need publisher confirmation
are listed in ENGINE_NOTES_KO.md.
"""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Mission:
    city: str
    number: int
    chips: tuple[int, int, int, int] | None = None
    pool: int | None = None
    faceup: tuple[int, ...] = ()
    setup_reveal: str | None = None
    held_player: int | None = None
    left_only: tuple[int, ...] = ()
    forbidden_right: tuple[int, ...] = ()
    forbidden_opposite: tuple[int, ...] = ()
    two_cards: tuple[int, ...] = ()
    completion_positions: tuple[tuple[int,int], ...] = ()
    color_positions: tuple[tuple[str,int], ...] = ()
    require_start_pass: bool = False
    target_sets: int = 4
    feedback: str = 'normal'
    extra_even_chip: bool = False
    guess_number: bool = False
    setup_pass_right: bool = False
    description: str = ''

ALL=(0,1,2,3)
M={}
def add(city,n,**kw):
    m=Mission(city,n,**kw)
    M[(city,n)]=m
    return m

# Seoul: verified chips from existing production server.
add('seoul',1,chips=(6,6,6,6),faceup=ALL,description='All players pass cards face up.')
add('seoul',2,chips=(5,5,5,5),setup_reveal='choose',description='Reveal one chosen card before play; it remains face up.')
add('seoul',3,chips=(5,4,5,5),setup_reveal='random',description='Reveal one random card before examining hands.')
add('seoul',4,chips=(6,6,4,5),faceup=(1,),description='Circle passes face up.')
add('seoul',5,chips=(6,6,6,6),description='Standard rules.')

# Berlin
add('berlin',1,chips=(5,5,5,5),completion_positions=((1,1),),description='Circle completes first.')
add('berlin',2,chips=(6,5,5,6),left_only=(3,),description='Star passes left only.')
add('berlin',3,chips=(6,4,5,6),two_cards=(3,),description='Star passes two; recipient chooses one and returns the other.')
add('berlin',4,chips=(5,5,5,5),completion_positions=((1,1),),left_only=(2,),description='Circle completes first; Square passes left only.')
add('berlin',5,chips=(5,4,4,5),feedback='count_color',description='Recipient declares count of received color; use negative side only.')

# New York
add('new_york',1,chips=(6,4,5,5),color_positions=(('blue',1),),description='Blue set completes first.')
add('new_york',2,chips=(6,6,6,6),setup_pass_right=True,require_start_pass=True,description='Simultaneous initial pass right. Complete only when passing Starting Card (except last).')
add('new_york',3,chips=(5,3,4,4),target_sets=2,description='Two sets suffice to win.')
add('new_york',4,chips=(5,5,5,5),color_positions=(('blue',1),),completion_positions=((0,2),),description='Blue first; Triangle second.')
add('new_york',5,chips=(6,6,6,6),require_start_pass=True,description='Complete only when passing Starting Card (except last).')

# Tokyo
add('tokyo',1,chips=(5,5,4,4),forbidden_opposite=ALL,description='No passes to opposite player.')
add('tokyo',2,chips=(5,5,5,5),faceup=(1,),forbidden_right=ALL,description='Circle face up; no right passes except with two players.')
add('tokyo',3,chips=(6,5,5,6),left_only=(0,),forbidden_opposite=(1,2,3),description='Triangle left only; others no opposite.')
add('tokyo',4,chips=(6,5,5,5),completion_positions=((1,2),),forbidden_opposite=ALL,color_positions=(('brown',4),),description='Circle second; no opposite; brown fourth.')
add('tokyo',5,chips=(6,5,5,6),forbidden_right=ALL,description='No right passes except with two players.')

# London
add('london',1,pool=18,description='18 chips shared.')
add('london',2,pool=24,extra_even_chip=True,description='24 shared chips; even card costs an additional chip.')
add('london',3,chips=(5,5,5,4),held_player=0,description='Triangle sets aside a random unseen card until anyone finishes.')
add('london',4,pool=23,guess_number=True,description='23 shared chips; receiver guesses number before looking; wrong costs one more.')
add('london',5,chips=(4,4,4,4),description='Standard rules.')

# Paris
add('paris',1,chips=(6,5,5,5),completion_positions=((0,1),(1,2),(2,3),(3,4)),description='Fixed completion order.')
add('paris',2,chips=(5,4,5,5),feedback='negative_only',two_cards=ALL,description='No informative feedback; two card offers.')
add('paris',3,pool=19,held_player=0,completion_positions=((0,2),),description='19 shared chips; Triangle holds card and finishes second.')
add('paris',4,chips=(6,5,5,5),completion_positions=((0,1),(2,3)),color_positions=(('magenta',2),),description='Triangle first, red second, Square third.')
add('paris',5,chips=(5,5,5,5),feedback='negative_only_triangle',left_only=(1,),color_positions=(('green',3),),description='Triangle no feedback; Circle passes left; green third.')

CITY_NAMES={'seoul':'Seoul','berlin':'Berlin','new_york':'New York','tokyo':'Tokyo','london':'London','paris':'Paris'}
CITY_ORDER=tuple(CITY_NAMES)
assert len(M)==30
