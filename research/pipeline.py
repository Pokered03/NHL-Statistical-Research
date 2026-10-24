"""Batch worker: validate, aggregate, backtest, then publish one atomic database."""
import argparse
import json
import os
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from .config import SPORT, EXPECTED_TEAMS, DEFAULT_SEASONS
from .store import DB_PATH,connect
from .sources import Fetcher,collect,SOURCES,mlb_season_reference,SourceError
from .metrics import METRICS
from .model import fit,adjusted_strength,backtest

def valid_game(g,teams):
    if not g.get('id') or g.get('home')==g.get('away'):raise ValueError('Invalid game identity')
    if g.get('home') not in teams or g.get('away') not in teams:raise ValueError('Unknown team identity')
    datetime.fromisoformat(g['date'])
    if g['status']=='final':
        for side in ('home_score','away_score'):
            if g[side] is None or g[side]<0 or g[side]>({'nfl':100,'cfb':150,'nba':250,'cbb':250,'mlb':60,'nhl':30}[SPORT]):raise ValueError('Invalid final score')

def ingest(c,teams,games,boxes,now):
    for t in teams.values():
        c.execute('INSERT INTO teams VALUES(:id,:name,:division,:conference) ON CONFLICT(id) DO UPDATE SET name=excluded.name,division=excluded.division,conference=excluded.conference',t)
    inferred=defaultdict(set)
    for g in games.values():
        inferred[g['home']].add(g['season']);inferred[g['away']].add(g['season'])
    for tid,t in teams.items():
        memberships=t.get('_seasons') or {year:{'name':t['name'],'division':t.get('division'),'conference':t.get('conference')} for year in inferred[tid]}
        for year,membership in memberships.items():
            c.execute('INSERT OR REPLACE INTO team_seasons VALUES(?,?,?,?,?)',(int(year),tid,membership['name'],membership.get('division'),membership.get('conference')))
    for g in games.values():
        valid_game(g,teams)
        if g['date']>now[:10] and g['status']=='final':raise ValueError('Source claims a future game is final')
        g={**g,'updated_at':now}
        cols=['id','season','date','start','home','away','neutral','status','home_score','away_score','venue','source','updated_at']
        c.execute('INSERT INTO games('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+') ON CONFLICT(id) DO UPDATE SET '+','.join(k+'=excluded.'+k for k in cols if k!='id'),[g[k] for k in cols])
        if g.get('_market'):
            c.execute('INSERT OR REPLACE INTO market_history VALUES(?,?,?,?)',(g['id'],g['_market']['home_spread'],g['_market']['total_line'],g['_market']['source']))
        if g['status']!='final':c.execute('DELETE FROM boxes WHERE game_id=?',(g['id'],))
    for (gid,tid),p in boxes.items():
        g=games.get(gid)
        if not g or g['status']!='final':continue
        if tid not in (g['home'],g['away']):raise ValueError('Box team does not participate in game')
        c.execute('INSERT INTO boxes VALUES(?,?,?) ON CONFLICT(game_id,team_id) DO UPDATE SET payload=excluded.payload',(gid,tid,json.dumps(p,allow_nan=False)))

def make_rows(games,boxes):
    out=defaultdict(list)
    for g in sorted(games,key=lambda x:(x['date'],x['id'])):
        if g['status']!='final':continue
        for team,opp,home in [(g['home'],g['away'],True),(g['away'],g['home'],False)]:
            p=boxes.get((g['id'],team),{}).copy();q=boxes.get((g['id'],opp),{})
            for k,v in q.items():p['opp_'+k]=v
            p.update({'points':g['home_score'] if home else g['away_score'],'allowed':g['away_score'] if home else g['home_score'],
              'date':g['date'],'game_id':g['id'],'opp':opp,'venue':'neutral' if g['neutral'] else 'home' if home else 'away'})
            p['margin']=p['points']-p['allowed'];p['win']=float(p['margin']>0) if p['margin'] else .5
            if out[team]:p['rest']=(datetime.fromisoformat(p['date'])-datetime.fromisoformat(out[team][-1]['date'])).days
            if SPORT=='nhl' and p.get('shots') is not None and q.get('saves') is not None and p['shots']>=q['saves']:p['actual_goals']=p['shots']-q['saves']
            if 'turnovers' in p and 'turnovers' in q:p['turnover_margin']=q['turnovers']-p['turnovers']
            if 'sacks_allowed' in q:p['sacks']=q['sacks_allowed']
            if 'half_sacks_allowed' in q:p['half_sacks']=q['half_sacks_allowed']
            if 'half_turnovers' in p and 'half_turnovers' in q:p['half_turnover_margin']=q['half_turnovers']-p['half_turnovers']
            if 'half_points' in q:p['half_allowed']=q['half_points']
            out[team].append(p)
    # FIP's season constant reconciles league FIP to league ERA; no external constant is invented.
    if SPORT=='mlb':
        allrows=[r for rs in out.values() for r in rs]
        valid=[r for r in allrows if all(r.get(k) is not None for k in ('opp_hr','opp_bb','opp_hbp','opp_so','outs','earned_runs'))]
        outs=sum(r['outs'] for r in valid)
        if outs>0:
            constant=27*sum(r['earned_runs'] for r in valid)/outs-3*sum(13*r['opp_hr']+3*(r['opp_bb']+r['opp_hbp'])-2*r['opp_so'] for r in valid)/outs
            for r in valid:r['fip_num']=13*r['opp_hr']+3*(r['opp_bb']+r['opp_hbp'])-2*r['opp_so'];r['fip_constant']=constant
    return out

def build_summaries(games,boxes,teams,m,season_refs=None):
    rows=make_rows(games,boxes);out={}
    for tid,rs in rows.items():
        splits={'Season':rs,'Last 3':rs[-3:],'Last 5':rs[-5:],'Last 10':rs[-10:],
          'Home':[r for r in rs if r['venue']=='home'],'Away':[r for r in rs if r['venue']=='away'],
          '1st half':[{**{k[5:]:v for k,v in r.items() if k.startswith('half_')},**{'opp_'+k[9:]:v for k,v in r.items() if k.startswith('opp_half_')},'points':r.get('half_points'),'allowed':r.get('half_allowed')} for r in rs if r.get('half_points') is not None]}
        stats={}
        for split,sr in splits.items():
            stats[split]={}
            for metric in METRICS:
                v,n=metric.value(sr)
                stats[split][metric.key]={'value':v,'n':n,'rank':None,'pop':0}
        strengths=[adjusted_strength(m,r['opp']) for r in rs];strengths=[x for x in strengths if x is not None]
        w=sum(r['margin']>0 for r in rs);l=sum(r['margin']<0 for r in rs);draw=len(rs)-w-l
        last=rs[-5:];trend=[r['points'] for r in rs[-10:]]
        out[tid]={'stats':stats,'games':len(rs),'record':f'{w}-{l}'+(f'-{draw}' if draw else ''),'last_date':rs[-1]['date'],
         'last5':[{'date':r['date'],'opp':r['opp'],'scored':r['points'],'allowed':r['allowed'],'venue':r['venue']} for r in last],
         'trend':trend,'defensive_trend':[r['allowed'] for r in rs[-10:]],'strength':adjusted_strength(m,tid),'sos':sum(strengths)/len(strengths) if strengths else None,
         'coverage':{'box_games':sum(bool(boxes.get((r['game_id'],tid))) for r in rs),'completed_games':len(rs)},
         'quality_record':{},'division':teams[tid].get('division')}
    if SPORT=='mlb' and season_refs:
        pitching_keys={'era','whip','fip','pk_rate','pbb_rate'}
        for tid,ref in season_refs.items():
            if tid not in out:continue
            payload=ref['payload']
            for key,value in payload['metrics'].items():
                if value is not None and key in out[tid]['stats']['Season']:
                    out[tid]['stats']['Season'][key]={'value':value,'n':payload['pitching_games'] if key in pitching_keys else payload['hitting_games'],'rank':None,'pop':0,'source_note':'Official MLB regular season; separate from rolling game-box scope.','source':ref['source'],'retrieved_at':ref['retrieved_at']}
    if SPORT in ('nba','cbb'):
        normalized=[]
        for g in games:
            a=boxes.get((g['id'],g['home']),{});b=boxes.get((g['id'],g['away']),{})
            if a.get('poss',0)>20 and b.get('poss',0)>20:
                normalized.append({**g,'home_score':100*g['home_score']/a['poss'],'away_score':100*g['away_score']/b['poss']})
        efficiency=fit(normalized)
        if efficiency:
            beta=efficiency['beta'];n=len(efficiency['teams'])
            for tid,payload in out.items():
                if tid not in efficiency['teams']:continue
                i=efficiency['teams'].index(tid)
                for key,value in [('adjusted_ortg',beta[0]+beta[2+i]),('adjusted_drtg',beta[0]+beta[2+n+i])]:
                    payload['stats']['Season'][key]={'value':value,'n':efficiency['counts'][tid],'rank':None,'pop':0}
    groups=defaultdict(list)
    for tid in out:groups[teams[tid].get('division') if SPORT=='cfb' else 'all'].append(tid)
    for group,ids in groups.items():
        strength=sorted([tid for tid in ids if out[tid]['strength'] is not None],key=lambda t:out[t]['strength'],reverse=True)
        pos={t:i for i,t in enumerate(strength)}
        for tid in ids:
            out[tid]['strength_rank']=pos.get(tid,0)+1 if tid in pos else None
            for label,select in [('stronger',lambda r:r['opp'] in pos and pos[r['opp']]<len(pos)/3),('weaker',lambda r:r['opp'] in pos and pos[r['opp']]>=2*len(pos)/3)]:
                sr=[r for r in rows[tid] if select(r)]
                out[tid]['quality_record'][label]={'wins':sum(r['margin']>0 for r in sr),'losses':sum(r['margin']<0 for r in sr),'games':len(sr)}
        for split in ('Season','Last 3','Last 5','Last 10','Home','Away','1st half'):
            for metric in METRICS:
                valid=[(tid,out[tid]['stats'][split][metric.key]['value']) for tid in ids if out[tid]['stats'][split][metric.key]['value'] is not None]
                if not metric.direction:continue
                valid.sort(key=lambda z:z[1]*metric.direction,reverse=True)
                previous=None;rank=0
                for i,(tid,v) in enumerate(valid):
                    if previous is None or abs(v-previous)>1e-9:rank=i+1
                    previous=v;out[tid]['stats'][split][metric.key].update({'rank':rank,'pop':len(valid)})
    return out

def quarantine_boxes(c):
    if SPORT not in ('nba','cbb'):return []
    invalid=set()
    for r in c.execute('SELECT b.game_id,b.team_id,b.payload,g.home,g.home_score,g.away_score FROM boxes b JOIN games g ON b.game_id=g.id'):
        p=json.loads(r['payload']);score=r['home_score'] if r['team_id']==r['home'] else r['away_score']
        if all(p.get(k) is not None for k in ('fgm','fg3m','ftm')) and abs(2*p['fgm']+p['fg3m']+p['ftm']-score)>.01:invalid.add(r['game_id'])
        if any(p.get(a) is not None and p.get(b) is not None and (p[a]<0 or p[a]>p[b]) for a,b in [('fgm','fga'),('fg3m','fg3a'),('ftm','fta'),('fg3a','fga')]):invalid.add(r['game_id'])
    for gid in invalid:c.execute('DELETE FROM boxes WHERE game_id=?',(gid,))
    old=c.execute("SELECT payload FROM metadata WHERE key='quality_audit'").fetchone();previous=json.loads(old[0]) if old else {}
    history=sorted(set(previous.get('quarantined_game_ids',[]))|invalid)
    c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('quality_audit',json.dumps({'quarantined_game_ids':history,'quarantined_this_run':len(invalid),'reason':'Shooting totals disagree with final score or violate shot-count consistency. Both teams’ box metrics excluded for affected games; final scores retained.'})))
    return sorted(invalid)


def rebuild(c,now,run_backtest=True,changed_seasons=None):
    quarantine_boxes(c)
    teams={r['id']:dict(r) for r in c.execute('SELECT * FROM teams')}
    allgames=[dict(r) for r in c.execute("SELECT * FROM games WHERE status='final' ORDER BY date,id")]
    markets={r['game_id']:dict(r) for r in c.execute('SELECT * FROM market_history')}
    for g in allgames:
        market=markets.get(g['id'],{});g['home_spread']=market.get('home_spread');g['market_total']=market.get('total_line')
    boxes={(r['game_id'],r['team_id']):json.loads(r['payload']) for r in c.execute('SELECT * FROM boxes')}
    for season in sorted({g['season'] for g in allgames}):
        if changed_seasons is not None and season not in changed_seasons:continue
        gs=[g for g in allgames if g['season']==season and g['date']<=now[:10]];m=fit(gs)
        if not m:continue
        season_teams={r['team_id']:{'id':r['team_id'],'name':r['name'],'division':r['division'],'conference':r['conference']} for r in c.execute('SELECT * FROM team_seasons WHERE season=?',(season,))}
        season_refs={r['team_id']:{'payload':json.loads(r['payload']),'source':r['source'],'retrieved_at':r['retrieved_at']} for r in c.execute('SELECT * FROM season_reference WHERE season=?',(season,))}
        summaries=build_summaries(gs,boxes,season_teams,m,season_refs)
        c.execute('DELETE FROM snapshots WHERE season=?',(season,))
        for tid,p in summaries.items():c.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(season,tid,now,json.dumps(p,allow_nan=False)))
        c.execute('INSERT OR REPLACE INTO models VALUES(?,?,?)',(season,now,json.dumps(m,allow_nan=False)))
    old=c.execute("SELECT payload FROM metadata WHERE key='validation'").fetchone()
    if run_backtest:
        report,oos=backtest(allgames)
        report['generated_at']=now
        c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('validation',json.dumps(report,allow_nan=False)))
        report_path=Path('reports');report_path.mkdir(exist_ok=True)
        (report_path/'backtest.json').write_text(json.dumps({k:v for k,v in report.items() if k not in ('margin_errors','total_errors')},indent=2))
        # Audit exact train/test dates without loading predictions in the dashboard.
        import csv
        if oos:
            with (report_path/'walk_forward_predictions.csv').open('w') as f:
                w=csv.DictWriter(f,fieldnames=list(oos[0]));w.writeheader();w.writerows(oos)
    elif old:
        report=json.loads(old[0]);report['gate']=False;report['reason']='Data changed without rerunning historical validation; PASS until validation refreshed.'
        c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('validation',json.dumps(report)))
    counts={str(r[0]):r[1] for r in c.execute('SELECT season,COUNT(*) FROM games GROUP BY season')}
    coverage=[]
    for season in map(int,counts):
        n=c.execute('SELECT COUNT(DISTINCT team_id) FROM snapshots WHERE season=?',(season,)).fetchone()[0]
        coverage.append({'season':season,'teams_with_completed_games':n,'registered_teams':c.execute('SELECT COUNT(*) FROM team_seasons WHERE season=?',(season,)).fetchone()[0],'schedule_games':counts[str(season)],'latest_final':max((g['date'] for g in allgames if g['season']==season),default=None)})
    data={'last_successful_update':now,'source':SOURCES[SPORT],'coverage':coverage,
      'expected_teams':EXPECTED_TEAMS,'sport':SPORT,'fixture':False,'warnings':[
       'CFB summaries cover FBS/FCS opponents only; games against lower divisions are excluded.' if SPORT=='cfb' else 'Team membership is season-specific; exhibition, All-Star, and non-Division-I opponents are excluded from basketball summaries.',
       'No verified injury/lineup/starting-pitcher/starting-goaltender/weather feeds are integrated.',
       'A successful download does not guarantee the publisher has current data. Check latest completed game and season coverage.',
       'Historical-season summaries are descriptive season-end research, not historical pregame snapshots.',
       'Rankings are within available observed teams; missing-team coverage can change rank percentiles.']}
    c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('status',json.dumps(data)))
    return data

def _refresh_unlocked(path=DB_PATH,seasons=None,advanced=False,run_backtest=True,live=True):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Keep the last good database on a failed download, schema change or validation error.
    now=datetime.now(timezone.utc).isoformat();fetch=Fetcher(path.parent/'raw_cache')
    teams,games,boxes=collect(fetch,seasons or DEFAULT_SEASONS,advanced,live)
    from .context import basketball_roles,mlb_upcoming_context
    team_contexts=basketball_roles(fetch,seasons or DEFAULT_SEASONS,games,boxes)
    if SPORT=='mlb' and live:mlb_upcoming_context(fetch,seasons or DEFAULT_SEASONS,games,teams)
    if not games:raise ValueError('No valid source games; refusing to publish an empty database')
    references=[];reference_error=None
    if SPORT=='mlb':
        try:references=mlb_season_reference(fetch,seasons or DEFAULT_SEASONS)
        except SourceError as exc:reference_error=str(exc)
    tmp=path.with_name(path.name+'.building')
    if tmp.exists():tmp.unlink()
    if path.exists():
        with sqlite3.connect(path) as src,sqlite3.connect(tmp) as dst:
            if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Existing database is corrupt; preserve it and restore a verified backup before refreshing')
            src.backup(dst)
    try:
        with connect(tmp,readonly=False) as c:
            ingest(c,teams,games,boxes,now)
            for context in team_contexts:
                c.execute('INSERT OR REPLACE INTO team_context VALUES(?,?,?,?,?)',(context['season'],context['team_id'],context['kind'],context['asof'],json.dumps(context['payload'],allow_nan=False)))
            for g in games.values():
                if g.get('_context'):c.execute('INSERT OR REPLACE INTO game_context VALUES(?,?,?)',(g['id'],g['_context']['retrieved_at'],json.dumps(g['_context'])))
            for ref in references:
                c.execute('INSERT OR REPLACE INTO season_reference VALUES(?,?,?,?,?,?)',(ref['season'],ref['team_id'],ref['scope'],ref['source'],ref['retrieved_at'],json.dumps(ref['payload'],allow_nan=False)))
            data=rebuild(c,now,run_backtest,set(seasons or DEFAULT_SEASONS))
            if reference_error:data['warnings'].append('Official MLB season summary refresh failed; any previously stored summary may be stale: '+reference_error)
            if references:
                c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('reference_sources',json.dumps([dict(r) for r in c.execute('SELECT season,scope,source,MAX(retrieved_at) retrieved_at,COUNT(*) teams FROM season_reference GROUP BY season,scope,source')])))
            if references:data['warnings'].append('MLB season cells marked with a dagger use official regular-season summaries. Rolling/home/away cells use available individual game boxes; these scopes must not be treated as identical.')
            data['source_checked_at']=now
            data['summaries_rebuilt_at']=now
            data['source_retrieved_at']=max((x.get('retrieved_at','') or '' for x in fetch.log),default=None)
            c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('status',json.dumps(data)))
            c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',('requests',json.dumps(fetch.log)))
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity failed')
        os.replace(tmp,path)
        return data
    finally:
        if tmp.exists():tmp.unlink()

def refresh(path=DB_PATH,seasons=None,advanced=False,run_backtest=True,live=True):
    # A scheduled refresh and a manual refresh must never publish the same file concurrently.
    import fcntl
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another refresh for this independent database is already running')
        try:return _refresh_unlocked(path,seasons,advanced,run_backtest,live)
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def main():
    p=argparse.ArgumentParser(description='Refresh this sport only; never calls an odds API')
    p.add_argument('--seasons',nargs='+',type=int,default=DEFAULT_SEASONS);p.add_argument('--advanced',action='store_true')
    p.add_argument('--skip-backtest',action='store_true');p.add_argument('--no-live',action='store_true')
    a=p.parse_args();print(json.dumps(refresh(seasons=a.seasons,advanced=a.advanced,run_backtest=not a.skip_backtest,live=not a.no_live),indent=2))
if __name__=='__main__':main()
