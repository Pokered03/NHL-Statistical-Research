from datetime import date,timedelta,datetime,timezone
import json
import pytest
from research.config import SPORT
from research.store import connect
from research.pipeline import ingest,rebuild

@pytest.fixture
def fixture_data():
    teams={str(i):{'id':str(i),'name':f'Test Team {i}','division':'FBS' if SPORT=='cfb' else SPORT.upper(),'conference':'test'} for i in range(4)}
    games={};boxes={};base={'nfl':23,'cfb':28,'nba':105,'cbb':70,'mlb':4,'nhl':3}[SPORT]
    for day in range(90):
        for j,(h,a) in enumerate([((day%3)+1,0),(1+(day+1)%3,1+(day+2)%3)]):
            gid=f'{day}-{j}';d=(date(2025,1,1)+timedelta(days=day)).isoformat()
            hs=base+(day*7+j*3)%9;aws=base+(day*5+j)%7
            g={'id':gid,'season':2025,'date':d,'start':d+'T19:00:00+00:00','home':str(h),'away':str(a),'neutral':int(day%8==0),'status':'final','home_score':hs,'away_score':aws,'venue':'Fixture venue','source':'SYNTHETIC TEST ONLY'}
            games[gid]=g
            for tid in (str(h),str(a)):
                boxes[(gid,tid)]={'fgm':30.,'fga':70.,'fg3m':10.,'fg3a':30.,'fta':20.,'oreb':8.,'dreb':25.,'tov':12.,'poss':82.8,'assists':15.,'yards':350.,'plays':65.,'pass_yards':230.,'rush_yards':120.,'turnovers':1.,'third_made':4.,'third_att':10.,'half_points':float(base//2),'shots':30.,'pp_goals':1.,'hits':8.,'ab':34.,'hits':8.,'bb':3.,'hbp':1.,'sf':1.,'sh':0.,'doubles':2.,'triples':0.,'hr':1.,'so':7.,'earned_runs':3.,'outs':27.}
    return teams,games,boxes

@pytest.fixture
def fixture_db(tmp_path,fixture_data):
    p=tmp_path/'test.sqlite';teams,games,boxes=fixture_data
    with connect(p,False) as c:
        ingest(c,teams,games,boxes,'2025-04-01T00:00:00+00:00')
        rebuild(c,'2025-04-01T00:00:00+00:00',False)
        status=json.loads(c.execute("SELECT payload FROM metadata WHERE key='status'").fetchone()[0]);status['fixture']=True
        c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('status',json.dumps(status)))
    return p
