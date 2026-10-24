import pytest
from research.config import SPORT

@pytest.mark.skipif(SPORT not in ('nba','cbb'),reason='Observed basketball roles only')
def test_observed_roles_require_score_and_start_reconciliation(monkeypatch):
    import research.context as ctx
    games={'g':{'id':'g','season':2025,'date':'2025-01-01','home':'H','away':'A','status':'final','home_score':10.,'away_score':8.}}
    rows=[]
    for tid,bench in [('H',5),('A',3)]:
        for i in range(6):rows.append({'game_id':'g','team_id':tid,'athlete_id':i,'athlete_display_name':f'{tid} Player {i}','minutes':10,'points':1 if i<5 else bench,'starter':i<5,'field_goals_attempted':2,'free_throws_attempted':0,'turnovers':0})
        rows.append({'game_id':'g','team_id':tid,'athlete_id':99,'minutes':None,'points':None,'starter':False})
    def batches(*a,**kw):yield from rows
    monkeypatch.setattr(ctx,'batches',batches)
    class Fetch:log=[]
    boxes={};contexts=ctx.basketball_roles(Fetch(),[2025],games,boxes)
    assert boxes[('g','H')]['bench']==5 and boxes[('g','A')]['bench']==3
    assert len(contexts)==2
    assert all(len(c['payload']['reported_starters'])==5 for c in contexts)
    assert all('live injury' in c['payload']['note'] for c in contexts)
    rows[0]['points']=9
    boxes={};contexts=ctx.basketball_roles(Fetch(),[2025],games,boxes)
    assert ('g','H') not in boxes
    assert len(contexts)==1
