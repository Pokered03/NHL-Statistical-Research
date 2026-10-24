"""Regression checks for observed source traps: exhibition teams and percentage semantics."""
import pandas as pd
from research.config import SPORT
from research.sources import basketball,game,register
from research.metrics import BY_KEY
import pytest

@pytest.mark.skipif(SPORT not in ('nba','cbb'),reason='Basketball adapter only')
def test_exhibition_and_non_d1_filter():
    rows=[]
    for gid,h,a in [(1,1,2),(2,1,9999)]:
        rows.append({'id':gid,'game_id':gid,'date':'2025-01-01T20:00:00Z','home_id':h,'away_id':a,'home_display_name':'A','away_display_name':'B' if a==2 else 'Exhibition','home_score':80,'away_score':70,'status_type_name':'STATUS_FINAL','neutral_site':False,'home_conference_id':1,'away_conference_id':1 if a==2 else None})
    class Fake:
        def parquet(self,url):
            if 'schedules/' in url:return pd.DataFrame(rows)
            if 'standings/' in url:return pd.DataFrame([{'team_id':i,'team_display_name':str(i),'group_name':'D-I','group_id':1} for i in [1,2]])
            return pd.DataFrame([{'game_id':1,'team_id':i,'field_goals_made':25,'field_goals_attempted':60,'three_point_field_goals_made':10,'three_point_field_goals_attempted':25,'free_throws_attempted':20,'offensive_rebounds':10,'defensive_rebounds':20,'total_turnovers':10} for i in [1,2]])
    teams,games,boxes=basketball(Fake(),[2025])
    assert set(games)=={'1'}
    assert '9999' not in teams
    assert abs(boxes[('1','1')]['poss']-68.8)<1e-8

@pytest.mark.skipif(SPORT!='mlb',reason='MLB metrics only')
def test_era_whip_fip_and_ops():
    rows=[{'earned_runs':3,'outs':27,'opp_hits':8,'opp_bb':2,'fip_num':9,'fip_constant':3.1,'hits':10,'ab':30,'bb':4,'hbp':1,'sf':1,'doubles':2,'triples':0,'hr':1}]
    assert BY_KEY['era'].value(rows)[0]==3
    assert BY_KEY['whip'].value(rows)[0]==pytest.approx(10/9)
    assert BY_KEY['fip'].value(rows)[0]==pytest.approx(4.1)
    assert BY_KEY['ops'].value(rows)[0]==pytest.approx(15/36+15/30)

@pytest.mark.skipif(SPORT!='nfl',reason='NFL passer rating only')
def test_passer_rating_perfect_and_missing():
    row={'pass_comp':20,'pass_att':20,'pass_yards':400,'pass_td':5,'pass_int':0}
    assert BY_KEY['passer_rating'].value([row])[0]==pytest.approx(158.3333333)
    assert BY_KEY['passer_rating'].value([{'pass_att':0}])==(None,0)

def test_season_membership_not_overwritten():
    teams={};register(teams,'1','Old name','FCS','Old Conference',2025);register(teams,'1','New name','FBS','New Conference',2026)
    assert teams['1']['_seasons'][2025]['division']=='FCS'
    assert teams['1']['_seasons'][2026]['division']=='FBS'

@pytest.mark.skipif(SPORT not in ('nba','cbb'),reason='Basketball consistency only')
def test_inconsistent_boxes_quarantined(fixture_db):
    import json
    from research.store import connect
    from research.pipeline import quarantine_boxes
    with connect(fixture_db,False) as c:
        row=c.execute('SELECT game_id,team_id,payload FROM boxes LIMIT 1').fetchone();p=json.loads(row['payload']);p['ftm']=999
        c.execute('UPDATE boxes SET payload=? WHERE game_id=? AND team_id=?',(json.dumps(p),row['game_id'],row['team_id']))
        bad=quarantine_boxes(c)
        assert row['game_id'] in bad
        assert c.execute('SELECT COUNT(*) FROM boxes WHERE game_id=?',(row['game_id'],)).fetchone()[0]==0
        assert c.execute('SELECT status FROM games WHERE id=?',(row['game_id'],)).fetchone()[0]=='final'

@pytest.mark.skipif(SPORT!='mlb',reason='MLB official season source only')
def test_official_mlb_totals_keep_scope_and_missing_values(tmp_path):
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from research.sources import mlb_season_reference
    year=datetime.now(ZoneInfo('America/New_York')).year
    hitting={'gamesPlayed':162,'avg':'.250','obp':'.330','slg':'.400','ops':'.730','homeRuns':162,'strikeOuts':1000,'baseOnBalls':500,'plateAppearances':6000}
    pitching={'gamesPlayed':162,'era':'4.00','whip':'1.25','outs':4374,'earnedRuns':648,'homeRuns':160,'baseOnBalls':480,'hitBatsmen':40,'strikeOuts':1300,'battersFaced':6100}
    d={'stats':[{'group':{'displayName':g},'splits':[{'team':{'id':i},'season':str(year),'stat':s} for i in range(1,31)]} for g,s in [('hitting',hitting),('pitching',pitching)]]}
    p=tmp_path/'totals.json';p.write_text(json.dumps(d))
    class Fake:
        def get(self,url,ttl=0):
            assert 'gameType=R' in url
            assert 'odds' not in url
            return p
    r=mlb_season_reference(Fake(),[year])
    assert len(r)==30 and r[0]['scope']=='regular_season'
    assert r[0]['payload']['metrics']['avg']==.25
    assert r[0]['payload']['metrics']['hr']==1
    assert r[0]['payload']['hitting_games']==162
    assert r[0]['payload']['metrics']['fip']==pytest.approx(4.)
