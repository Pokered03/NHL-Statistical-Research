import json,math
from pathlib import Path
import pytest
from research.metrics import Metric,ratio,color,advantage
from research.pipeline import ingest,valid_game,build_summaries
from research.model import fit,scores,backtest,assessment
from research.store import connect,snapshot,schedule
from research.sources import status,num,when,Fetcher,SourceError
from research.view import table,header,confidence_cards

def test_ratios_weighted_not_averaged():
    m=ratio('x','test','Offense',[('n',1)],[('d',1)])
    v,n=m.value([{'n':1,'d':2},{'n':1,'d':8}]);assert v==20 and n==2

def test_missing_not_zero():
    m=ratio('x','test','Defense',[('n',1)],[('d',1)],direction=-1)
    assert m.value([{'n':0}])==(None,0)
    assert m.value([{'n':0,'d':10}])==(0.,1)
    assert m.value([{'n':1,'d':0}])==(None,1)

@pytest.mark.parametrize('a,b,d,want',[(10,20,1,'B'),(10,20,-1,'A'),(0,0,1,'EVEN'),(None,2,1,'—'),(1,2,0,'—')])
def test_statistic_direction(a,b,d,want):assert advantage(a,b,d)==want

def test_rank_colors():
    assert color(1,30)=='good';assert color(15,30)=='average';assert color(30,30)=='poor';assert color(None,30)=='missing'

def test_source_normalization():
    assert status('STATUS_FINAL')=='final';assert status('POSTPONED')=='postponed';assert status('CANCELLED')=='cancelled'
    assert status('STATUS_IN_PROGRESS')=='live';assert status('OFF')=='final'
    assert num('nan') is None;assert num(None) is None
    day,ts=when('2026-10-25T02:00:00Z');assert day=='2026-10-24';assert ts.endswith('+00:00')

def test_no_paid_hosts(tmp_path):
    with pytest.raises(SourceError):Fetcher(tmp_path).get('https://api.the-odds-api.com/v4/sports')

def test_reject_bad_ids(fixture_data):
    t,g,b=fixture_data;row=next(iter(g.values())).copy();row['home']=row['away']
    with pytest.raises(ValueError):valid_game(row,t)
    row=next(iter(g.values())).copy();row['away']='missing'
    with pytest.raises(ValueError):valid_game(row,t)

def test_duplicates_and_corrections(fixture_db,fixture_data):
    t,g,b=fixture_data
    with connect(fixture_db,False) as c:
        before=c.execute('SELECT COUNT(*) FROM games').fetchone()[0]
        ingest(c,t,g,b,'2025-04-02T00:00:00+00:00');assert c.execute('SELECT COUNT(*) FROM games').fetchone()[0]==before
        row=next(iter(g.values())).copy();row['home_score']+=1
        ingest(c,t,{row['id']:row},{},'2025-04-03T00:00:00+00:00')
        assert c.execute('SELECT home_score FROM games WHERE id=?',(row['id'],)).fetchone()[0]==row['home_score']
        row.update(status='postponed',home_score=None,away_score=None)
        ingest(c,t,{row['id']:row},{},'2025-04-03T00:00:00+00:00')
        assert c.execute('SELECT COUNT(*) FROM boxes WHERE game_id=?',(row['id'],)).fetchone()[0]==0

def test_summaries_and_first_half(fixture_db):
    s=snapshot(2025,'0',fixture_db)
    assert s['stats']['Last 3']['points']['n']==3
    assert s['stats']['Last 5']['points']['n']==5
    assert s['stats']['Last 10']['points']['n']==10
    assert s['stats']['1st half']['points']['value'] is not None
    assert s['stats']['Season']['allowed']['rank'] is not None
    assert len(schedule(2025,'2025-01-01',fixture_db))==2

def test_model_positive_finite_and_independent(fixture_data):
    t,g,b=fixture_data;m=fit(list(g.values()));s=scores(m,'0','1')
    assert all(math.isfinite(x) and x>0 for x in s)
    assert scores(m,'0','0') is None;assert scores(m,'0','unknown') is None

def test_no_fabricated_confidence(fixture_data):
    t,g,b=fixture_data;m=fit(list(g.values()));r=assessment(m,None,'0','1',spread=-3,total=100)
    assert r['status']=='PASS' and r['win_probability'] is None and r['confidence_score'] is None
    assert r['spread_status']=='PASS' and r['total_status']=='PASS'
    assert assessment(None,None,'0','1')['status']=='PASS'

def test_walk_forward_excludes_future(fixture_data):
    t,g,b=fixture_data;report,rows=backtest(list(g.values()))
    assert rows
    assert all(r['training_last_date']<r['date'] for r in rows)
    assert not report['gate']  # deliberately small synthetic validation set
    if report.get('status')=='tested':assert report['calibration_through']<report['test_from']

def test_html_escaped(fixture_db):
    s=snapshot(2025,'0',fixture_db)
    h=table('Offense',s,s,'<script>','B')+header('<script>','B',s,s,'<img>')
    assert '<script>' not in h and '&lt;script&gt;' in h

def test_moneyline_labels():
    h=confidence_cards({'win_probability':.8,'confidence_score':60,'margin':2,'total':5},'Away','Home')
    assert '20.0% / 80.0%' in h

def test_readonly_sql(fixture_db):
    with connect(fixture_db) as c:
        with pytest.raises(Exception):c.execute('DELETE FROM games')

def test_independent_runtime():
    root=Path(__file__).resolve().parents[1]
    assert (root/'research/config.py').exists()
    assert 'Multi-Sport-Value-Engine' not in (root/'app.py').read_text()

def test_failed_refresh_preserves_last_good_database(fixture_db,monkeypatch):
    import research.pipeline as p
    before=fixture_db.read_bytes()
    def fail(*a,**kw):raise RuntimeError('Controlled source outage')
    monkeypatch.setattr(p,'collect',fail)
    with pytest.raises(RuntimeError):p.refresh(fixture_db,seasons=[2025])
    assert fixture_db.read_bytes()==before
    with connect(fixture_db) as c:assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

def test_concurrent_refresh_rejected(fixture_db):
    import fcntl
    from research.pipeline import refresh
    lock=fixture_db.with_suffix('.lock')
    with lock.open('w') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError,match='already running'):refresh(fixture_db,seasons=[2025])
        fcntl.flock(f,fcntl.LOCK_UN)

def test_lightweight_online_matches_worker(fixture_data):
    from research import predict
    t,g,b=fixture_data;m=fit(list(g.values()))
    assert predict.scores(m,'0','1')==pytest.approx(scores(m,'0','1'))
    validation={'gate':True,'margin_sd':10,'calibrator':{'intercept':.1,'slope':.9},'margin_q10':-10,'margin_q90':10,'total_q10':-10,'total_q90':10,'margin_errors':[-1,0,1],'total_errors':[-2,0,2]}
    a=assessment(m,validation,'0','1',spread=-2,total=10)
    r=predict.assessment(m,validation,'0','1',spread=-2,total=10)
    assert r['win_probability']==pytest.approx(a['win_probability'],abs=1e-10)
    assert r['spread_probability']==a['spread_probability']
    assert r['over_probability']==a['over_probability']
    assert predict.assessment(m,None,'0','1')['status']=='PASS'

def test_poisson_online_reference():
    from research.predict import poisson_win
    from scipy.stats import skellam
    for h,a in [(1.,1.),(4.,3.),(12.,6.),(.05,.05),(30.,1.)]:
        reference=1-skellam.cdf(0,h,a)+.5*skellam.pmf(0,h,a)
        assert poisson_win(h,a)==pytest.approx(reference,abs=1e-10)
