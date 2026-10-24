"""Free-source adapters. No odds endpoints, no secret discovery, no web-process HTTP."""
import csv
import gzip
import hashlib
import io
import json
import math
import re
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .config import SPORT

RAW='https://raw.githubusercontent.com/'
SDV=RAW+'sportsdataverse/'
ALLOWED={'raw.githubusercontent.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','www.retrosheet.org','statsapi.mlb.com'}
NY=ZoneInfo('America/New_York')
SOURCES={
'nfl':{'name':'nflverse / nflverse-data','url':'https://github.com/nflverse/nflverse-data','license':'CC BY 4.0; modified by this research application'},
'nba':{'name':'hoopR NBA / SportsDataverse','url':'https://github.com/sportsdataverse/hoopR-nba-data','license':'CC BY 4.0; modified by this research application'},
'cbb':{'name':'hoopR MBB / SportsDataverse','url':'https://github.com/sportsdataverse/hoopR-mbb-data','license':'CC BY 4.0; modified by this research application'},
'cfb':{'name':'cfbfastR / SportsDataverse','url':'https://github.com/sportsdataverse/cfbfastR-cfb-data','license':'Upstream open-data publication; confirm dataset-specific redistribution terms before public release.'},
'nhl':{'name':'fastRhockey / SportsDataverse','url':'https://github.com/sportsdataverse/fastRhockey-nhl-data','license':'MIT repository license; original NHL data/trademark rights retained.'},
'mlb':{'name':'Retrosheet (history); baseballr / SportsDataverse (current schedule)','url':'https://www.retrosheet.org/gamelogs/index.html','license':'The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at www.retrosheet.org. Current MLB schedule is republished by SportsDataverse/baseballr-data; original MLB rights retained. Personal research deployment only pending redistribution review.'}}

class SourceError(RuntimeError):pass
class Fetcher:
    def __init__(self,cache,max_bytes=80_000_000):
        self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True);self.max_bytes=max_bytes;self.log=[]
    def get(self,url,ttl=1800):
        from urllib.parse import urlparse
        if urlparse(url).hostname not in ALLOWED:raise SourceError('Unapproved source host')
        key=hashlib.sha256(url.encode()).hexdigest();p=self.cache/key;meta=self.cache/(key+'.json')
        m=json.loads(meta.read_text()) if meta.exists() else {}
        if p.exists() and time.time()-m.get('checked',0)<ttl:
            self.log.append({'url':url,'cache':True,'retrieved_at':m.get('retrieved_at')});return p
        headers={'User-Agent':'IndependentSportsResearch/1.0 (personal research; cached requests)'}
        if m.get('etag'):headers['If-None-Match']=m['etag']
        if m.get('last_modified'):headers['If-Modified-Since']=m['last_modified']
        for attempt in range(3):
            tmp=p.with_suffix('.part')
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45) as r:
                    count=0
                    with tmp.open('wb') as f:
                        while True:
                            b=r.read(128*1024)
                            if not b:break
                            count+=len(b)
                            if count>self.max_bytes:raise SourceError('Source exceeds worker download limit')
                            f.write(b)
                    tmp.replace(p);m={'etag':r.headers.get('ETag'),'last_modified':r.headers.get('Last-Modified'),'checked':time.time(),'retrieved_at':datetime.now(timezone.utc).isoformat(),'url':url}
                    meta.write_text(json.dumps(m));self.log.append(m);time.sleep(.15);return p
            except urllib.error.HTTPError as e:
                if e.code==304 and p.exists():m['checked']=time.time();meta.write_text(json.dumps(m));self.log.append(m);return p
                if e.code not in (429,500,502,503,504) or attempt==2:raise SourceError(f'Source HTTP {e.code}: {url}') from e
                time.sleep(min(float(e.headers.get('Retry-After','2')),30)*(attempt+1))
            except (OSError,TimeoutError) as e:
                if attempt==2:raise SourceError(f'Source unavailable: {url}') from e
                time.sleep(attempt+1)
            finally:
                if tmp.exists():tmp.unlink()
        raise SourceError('Source request failed')
    def parquet(self,url):
        import pandas as pd
        return pd.read_parquet(self.get(url))

def num(x):
    try:
        y=float(x);return y if math.isfinite(y) else None
    except (TypeError,ValueError):return None

def sid(x):
    if x is None or (isinstance(x,float) and math.isnan(x)):return None
    return str(int(x)) if isinstance(x,(float,int)) else str(x)

def clean(d):return {str(k):v for k,v in d.items() if v is not None and (not isinstance(v,float) or math.isfinite(v))}
def truth(x):return str(x).lower() in ('true','1','1.0')
def status(x):
    x=str(x).upper()
    if any(t in x for t in ('POSTPON','PPD')):return 'postponed'
    if any(t in x for t in ('CANCEL','CANC')):return 'cancelled'
    if 'SUSPEND' in x:return 'suspended'
    if any(t in x for t in ('FINAL','COMPLETE','OFF')):return 'final'
    if x in ('FINAL','OVER','7'):return 'final'
    if any(t in x for t in ('LIVE','IN_PROGRESS','IN PROGRESS','CRIT')):return 'live'
    return 'scheduled'

def when(value):
    if value is None:return None,None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if d.tzinfo is None:d=d.replace(tzinfo=NY)
        return d.astimezone(NY).date().isoformat(),d.astimezone(timezone.utc).isoformat()
    except ValueError:return None,None

def game(gid,season,home,away,date,start,hs,aws,st,neutral=False,venue=''):
    return {'id':sid(gid),'season':int(season),'home':sid(home),'away':sid(away),'date':date,'start':start,
      'home_score':num(hs) if st=='final' else None,'away_score':num(aws) if st=='final' else None,
      'status':st,'neutral':int(neutral),'venue':str(venue or ''),'source':SOURCES[SPORT]['name']}

def register(teams,tid,name,division,conference,year):
    old=teams.get(tid,{})
    memberships=old.get('_seasons',{}).copy()
    memberships[int(year)]={'name':str(name),'division':str(division),'conference':str(conference or '')}
    teams[tid]={'id':tid,'name':str(name),'division':str(division),'conference':str(conference or ''),'_seasons':memberships}


def basketball(fetch,seasons):
    repo='hoopR-nba-data' if SPORT=='nba' else 'hoopR-mbb-data';prefix='nba' if SPORT=='nba' else 'mbb'
    teams={};games={};boxes={}
    for year in seasons:
        try:s=fetch.parquet(f'{SDV}{repo}/main/{prefix}/schedules/parquet/{prefix}_schedule_{year}.parquet')
        except SourceError:
            if year==max(seasons):continue
            raise
        allowed=None
        if SPORT=='nba':allowed={str(i) for i in range(1,31)}
        else:
            try:standings=fetch.parquet(f'{SDV}{repo}/main/{prefix}/standings/parquet/standings_{year}.parquet')
            except SourceError:
                if year!=max(seasons):raise
                standings=fetch.parquet(f'{SDV}{repo}/main/{prefix}/standings/parquet/standings_{year-1}.parquet')
            allowed={sid(t) for t in standings['team_id'].dropna().unique()}
            conference_ids={sid(t) for t in standings['group_id'].dropna().unique()}
            for side in ('home','away'):
                if side+'_conference_id' in s.columns:
                    allowed.update(sid(r[side+'_id']) for r in s.to_dict('records') if sid(r.get(side+'_conference_id')) in conference_ids)
            for r in standings.drop_duplicates('team_id').to_dict('records'):
                tid=sid(r['team_id']);register(teams,tid,r['team_display_name'],'D-I',r.get('group_name',''),year)
        for r in s.to_dict('records'):
            if sid(r.get('home_id')) not in allowed or sid(r.get('away_id')) not in allowed:continue
            for side in ('home','away'):
                tid=sid(r.get(side+'_id'))
                if tid:register(teams,tid,r.get(side+'_display_name') or tid,'NBA' if SPORT=='nba' else 'D-I',teams.get(tid,{}).get('conference') or sid(r.get(side+'_conference_id')),year)
            date,start=when(r.get('date',r.get('game_date_time')))
            if not date:continue
            st=status(r.get('status_type_name'))
            g=game(r.get('game_id',r['id']),year,r['home_id'],r['away_id'],date,start,r.get('home_score'),r.get('away_score'),st,truth(r.get('neutral_site')),r.get('venue_full_name',''))
            games[g['id']]=g
        try:b=fetch.parquet(f'{SDV}{repo}/main/{prefix}/team_box/parquet/team_box_{year}.parquet')
        except SourceError:continue
        mp={'field_goals_made':'fgm','field_goals_attempted':'fga','three_point_field_goals_made':'fg3m','three_point_field_goals_attempted':'fg3a','free_throws_made':'ftm','free_throws_attempted':'fta','offensive_rebounds':'oreb','defensive_rebounds':'dreb','total_turnovers':'tov','assists':'assists','blocks':'blocks','steals':'steals','points_in_paint':'paint'}
        for r in b.to_dict('records'):
            gid=sid(r['game_id']);tid=sid(r['team_id']);g=games.get(gid)
            if not g or g['status']!='final' or tid not in (g['home'],g['away']):continue
            p={k:num(r.get(src)) for src,k in mp.items()};p=clean(p)
            if 'tov' not in p:p['tov']=num(r.get('turnovers'))
            if all(p.get(k) is not None for k in ['fga','oreb','tov','fta']):p['poss_raw']=p['fga']-p['oreb']+p['tov']+.44*p['fta']
            boxes[(gid,tid)]=clean(p)
        # Parse known line-score dictionaries without executing provider strings.
        for r in s.to_dict('records'):
            gid=sid(r.get('game_id',r['id']))
            for side in ('home','away'):
                vals=re.findall(r"'value':\s*([0-9.]+)",str(r.get(side+'_linescores','')))
                periods=2 if SPORT=='nba' else 1
                if len(vals)>=periods and (gid,sid(r.get(side+'_id'))) in boxes:
                    boxes[(gid,sid(r[side+'_id']))]['half_points']=sum(float(v) for v in vals[:periods])
    # Preserve the source possession convention, averaging both sides when both are available.
    for g in games.values():
        a=boxes.get((g['id'],g['home']),{});b=boxes.get((g['id'],g['away']),{})
        if a.get('poss_raw') and b.get('poss_raw'):a['poss']=b['poss']=(a['poss_raw']+b['poss_raw'])/2
    return teams,games,boxes

def college_football(fetch,seasons,advanced=False):
    repo='cfbfastR-cfb-data';teams={};games={};boxes={}
    for year in seasons:
        t=fetch.parquet(f'{SDV}{repo}/main/cfb/cfb_teams/parquet/cfb_teams_{year}.parquet')
        for r in t.to_dict('records'):
            div=str(r.get('classification') or '').lower()
            if truth(r.get('is_all_star')) or str(r.get('display_name','')).upper() in ('TBA','TBD'):continue
            if 'fbs' not in div and 'fcs' not in div:continue
            tid=sid(r['team_id']);register(teams,tid,r['display_name'],'FBS' if 'fbs' in div else 'FCS',r.get('conference_name') or r.get('cfbd_conference') or '',year)
        # Full FBS + FCS schedule, including FCS-only games (not the narrower ESPN mirror).
        s=fetch.parquet(f'{SDV}{repo}/main/cfb/cfb_schedules/parquet/cfb_schedules_{year}.parquet')
        for r in s.to_dict('records'):
            h=sid(r['home_id']);a=sid(r['away_id'])
            if h not in teams or a not in teams:continue
            date,start=when(r['start_date'])
            st=status(r.get('status'))
            if truth(r.get('completed')):st='final'
            g=game(r['game_id'],year,h,a,date,start,r.get('home_points'),r.get('away_points'),st,truth(r.get('neutral_site')),r.get('venue'))
            if date:games[g['id']]=g
        try:b=fetch.parquet(f'{SDV}{repo}/main/cfb/team_box/parquet/team_box_{year}.parquet')
        except SourceError:continue
        for r in b.to_dict('records'):
            gid=sid(r['game_id']);tid=sid(r['team_id'])
            if gid not in games or tid not in (games[gid]['home'],games[gid]['away']):continue
            p={'yards':num(r.get('totalYards')),'pass_yards':num(r.get('netPassingYards')),'rush_yards':num(r.get('rushingYards')),'turnovers':num(r.get('turnovers'))}
            z=re.fullmatch(r'(\d+)[/-](\d+)',str(r.get('completionAttempts','')))
            if z and num(r.get('rushingAttempts')) is not None:p['plays']=int(z[2])+float(r['rushingAttempts'])
            z=re.fullmatch(r'(\d+)[/-](\d+)',str(r.get('thirdDownEff','')))
            if z:p['third_made'],p['third_att']=int(z[1]),int(z[2])
            z=re.fullmatch(r'(\d+)-(\d+)',str(r.get('totalPenaltiesYards','')))
            if z:p['penalty_yards']=int(z[2])
            boxes[(gid,tid)]=clean(p)
    if advanced:
        from .events import enrich_college
        enrich_college(fetch,seasons,games,boxes)
    return teams,games,boxes

NFL_NAMES={'ARI':'Arizona Cardinals','ATL':'Atlanta Falcons','BAL':'Baltimore Ravens','BUF':'Buffalo Bills','CAR':'Carolina Panthers','CHI':'Chicago Bears','CIN':'Cincinnati Bengals','CLE':'Cleveland Browns','DAL':'Dallas Cowboys','DEN':'Denver Broncos','DET':'Detroit Lions','GB':'Green Bay Packers','HOU':'Houston Texans','IND':'Indianapolis Colts','JAX':'Jacksonville Jaguars','KC':'Kansas City Chiefs','LA':'Los Angeles Rams','LAC':'Los Angeles Chargers','LV':'Las Vegas Raiders','MIA':'Miami Dolphins','MIN':'Minnesota Vikings','NE':'New England Patriots','NO':'New Orleans Saints','NYG':'New York Giants','NYJ':'New York Jets','PHI':'Philadelphia Eagles','PIT':'Pittsburgh Steelers','SEA':'Seattle Seahawks','SF':'San Francisco 49ers','TB':'Tampa Bay Buccaneers','TEN':'Tennessee Titans','WAS':'Washington Commanders'}
def nfl(fetch,seasons,advanced=False):
    teams={k:{'id':k,'name':v,'division':'NFL','conference':''} for k,v in NFL_NAMES.items()};games={};boxes={}
    with fetch.get(RAW+'nflverse/nfldata/master/data/games.csv').open() as f:
        for r in csv.DictReader(f):
            if int(r['season']) not in seasons or r['game_type']=='PRE':continue
            if r['home_team'] not in teams or r['away_team'] not in teams:continue
            date,start=when(r['gameday']+'T'+(r.get('gametime') or '12:00'))
            hs,aws=num(r['home_score']),num(r['away_score'])
            st='final' if hs is not None and aws is not None else 'scheduled'
            g=game(r['game_id'],r['season'],r['home_team'],r['away_team'],date,start,hs,aws,st,r.get('location')=='Neutral',r.get('stadium'))
            if st=='final':g['_market']={'home_spread':-num(r['spread_line']) if num(r.get('spread_line')) is not None else None,'total_line':num(r.get('total_line')),'source':'nflverse/nfldata schedule closing lines; home spread sign normalized'}
            games[g['id']]=g
    if advanced:
        for year in seasons:
            url=f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.csv.gz'
            path=fetch.get(url,ttl=86400 if year<max(seasons) else 1800)
            redzone={};halftime={}
            with gzip.open(path,'rt') as f:
                for r in csv.DictReader(f):
                    gid=r.get('game_id');tid=r.get('posteam');g=games.get(gid)
                    if not g or g['status']!='final':continue
                    if r.get('qtr')=='2':
                        hs,aws=num(r.get('total_home_score')),num(r.get('total_away_score'))
                        if hs is not None and aws is not None:halftime[gid]=(hs,aws)
                    if tid not in (g['home'],g['away']):continue
                    p=boxes.setdefault((gid,tid),{})
                    def add(k,v):
                        v=num(v)
                        if v is not None:
                            p[k]=p.get(k,0)+v
                            if r.get('qtr') in ('1','2'):p['half_'+k]=p.get('half_'+k,0)+v
                    if r.get('play_type') not in ('pass','run') or r.get('no_play')=='1':continue
                    add('plays',1);add('yards',r.get('yards_gained'));add('pass_yards',r.get('passing_yards'));add('rush_yards',r.get('rushing_yards'))
                    e=num(r.get('epa'))
                    if e is not None:add('epa_sum',e);add('epa_n',1);add('success',e>0)
                    add('sacks_allowed',r.get('sack'));add('pass_td',r.get('pass_touchdown'));add('rush_td',r.get('rush_touchdown'))
                    if num(r.get('pass_attempt'))==1 and num(r.get('sack'))!=1:
                        add('pass_att',1);add('pass_comp',r.get('complete_pass'));add('pass_int',r.get('interception'))
                    yd=num(r.get('yardline_100'));drive=r.get('fixed_drive') or r.get('drive')
                    if yd is not None and yd<=20 and drive:
                        entry=redzone.setdefault((gid,tid),{'trips':set(),'td':set()});entry['trips'].add(drive)
                        if num(r.get('pass_touchdown'))==1 or num(r.get('rush_touchdown'))==1:entry['td'].add(drive)
                    add('third_made',r.get('third_down_converted'));add('third_att',r.get('down')=='3')
                    add('turnovers',(num(r.get('interception')) or 0)+(num(r.get('fumble_lost')) or 0))
                    y=num(r.get('yards_gained'))
                    add('explosive',y is not None and ((r.get('play_type')=='pass' and y>=20) or (r.get('play_type')=='run' and y>=10)))
            for (gid,tid),z in redzone.items():
                boxes[(gid,tid)]['rz_trips']=len(z['trips']);boxes[(gid,tid)]['rz_td']=len(z['td'])
            for gid,(hs,aws) in halftime.items():
                for team,points in [(games[gid]['home'],hs),(games[gid]['away'],aws)]:
                    if (gid,team) in boxes:boxes[(gid,team)]['half_points']=points
            # Absent zero events are zero only within observed play data, never for a missing box.
            for (gid,tid),p in boxes.items():
                if games[gid]['season']==year:
                    p['explosive_att']=p.get('plays',0)
                    for k in ['pass_yards','rush_yards','pass_td','rush_td','sacks_allowed','turnovers','third_made','third_att','explosive','pass_comp','pass_att','pass_int']:p.setdefault(k,0.)
    return teams,games,boxes

# Retrosheet canonical franchise identifiers and current MLB Stats API IDs.
MLB_TEAMS={'ANA':(108,'Los Angeles Angels'),'ARI':(109,'Arizona Diamondbacks'),'ATL':(144,'Atlanta Braves'),'BAL':(110,'Baltimore Orioles'),'BOS':(111,'Boston Red Sox'),'CHA':(145,'Chicago White Sox'),'CHN':(112,'Chicago Cubs'),'CIN':(113,'Cincinnati Reds'),'CLE':(114,'Cleveland Guardians'),'COL':(115,'Colorado Rockies'),'DET':(116,'Detroit Tigers'),'HOU':(117,'Houston Astros'),'KCA':(118,'Kansas City Royals'),'LAN':(119,'Los Angeles Dodgers'),'MIA':(146,'Miami Marlins'),'MIL':(158,'Milwaukee Brewers'),'MIN':(142,'Minnesota Twins'),'NYA':(147,'New York Yankees'),'NYN':(121,'New York Mets'),'OAK':(133,'Athletics'),'PHI':(143,'Philadelphia Phillies'),'PIT':(134,'Pittsburgh Pirates'),'SDN':(135,'San Diego Padres'),'SEA':(136,'Seattle Mariners'),'SFN':(137,'San Francisco Giants'),'SLN':(138,'St. Louis Cardinals'),'TBA':(139,'Tampa Bay Rays'),'TEX':(140,'Texas Rangers'),'TOR':(141,'Toronto Blue Jays'),'WAS':(120,'Washington Nationals')}
def baseball(fetch,seasons,live=True):
    teams={str(v[0]):{'id':str(v[0]),'name':v[1],'division':'MLB','conference':''} for v in MLB_TEAMS.values()};games={};boxes={}
    codes={k:str(v[0]) for k,v in MLB_TEAMS.items()};codes.update({'ATH':'133','FLO':'146','MON':'120'})
    for year in seasons:
        if year>=datetime.now(NY).year:continue  # Retrosheet season archive is published after completion.
        path=fetch.get(f'https://www.retrosheet.org/gamelogs/gl{year}.zip',ttl=86400*30)
        with zipfile.ZipFile(path) as z:
            fn=next(x for x in z.namelist() if x.upper().endswith('.TXT'))
            for r in csv.reader(io.TextIOWrapper(z.open(fn),encoding='utf-8-sig')):
                if r[3] not in codes or r[6] not in codes:continue
                day=datetime.strptime(r[0],'%Y%m%d').date().isoformat();gid='retro-'+r[6]+r[0]+'-'+r[1]
                hs,aws=num(r[10]),num(r[9])
                if hs is None or aws is None:continue
                g=game(gid,year,codes[r[6]],codes[r[3]],day,None,hs,aws,'final',False,r[16]);games[gid]=g
                for tid,offset,eridx,outs in [(g['away'],21,41,None),(g['home'],49,69,num(r[11]))]:
                    p={k:num(r[offset+i]) for i,k in enumerate(['ab','hits','doubles','triples','hr','rbi','sh','sf','hbp','bb','ibb','so'])}
                    # Defensive putouts give exact pitching outs, including walk-offs and extra innings.
                    p['outs']=num(r[71 if tid==g['home'] else 43])
                    # Individual earned runs allowed (not opponent batting field).
                    p['earned_runs']=num(r[40 if tid==g['away'] else 68])
                    boxes[(gid,tid)]=clean(p)
    if live:
        # Published schedule archive: one cached season file, no per-game API fan-out.
        current=datetime.now(NY).year
        for year in [y for y in seasons if y>=current]:
            try:s=fetch.parquet(f'{SDV}baseballr-data/main/mlb/schedule/{year}.parquet')
            except SourceError:continue
            for r in s.to_dict('records'):
                if str(r.get('game_type')) not in ('R','F','D','L','W'):continue
                h=sid(r['home_team_id']);a=sid(r['away_team_id'])
                if h not in teams or a not in teams:continue
                date,ts=when(r.get('game_datetime'))
                if not date:date=str(r['game_date'])[:10]
                st=status(r.get('detailed_state',r.get('abstract_state','')))
                g=game('mlb-'+str(r['game_pk']),year,h,a,date,ts,r.get('home_score'),r.get('away_score'),st,False,r.get('venue_name',''))
                games[g['id']]=g
    return teams,games,boxes

def hockey(fetch,seasons,advanced=False):
    repo='fastRhockey-nhl-data';teams={};games={};boxes={}
    for year in seasons:
        try:s=fetch.parquet(f'{SDV}{repo}/main/nhl/schedules/parquet/nhl_schedule_{year}.parquet')
        except SourceError:
            if year==max(seasons):continue
            raise
        for r in s.to_dict('records'):
            typ=str(r.get('game_type',''))
            if typ not in ('2','3','R','P','REG','POST','02','03'):continue
            h=str(r['home_team_abbr']);a=str(r['away_team_abbr'])
            for side in ('home','away'):
                tid=str(r[side+'_team_abbr']);register(teams,tid,r.get(side+'_team_name') or tid,'NHL','',year)
            date,start=when(r.get('game_time'))
            if not date:date=str(r['game_date'])[:10];start=None
            st=status(r.get('game_state',''))
            g=game(r['game_id'],year,h,a,date,start,r.get('home_score'),r.get('away_score'),st,False,r.get('venue',''));games[g['id']]=g
        try:b=fetch.parquet(f'{SDV}{repo}/main/nhl/team_box/parquet/team_box_{year}.parquet')
        except SourceError:continue
        for r in b.to_dict('records'):
            gid=sid(r['game_id']);tid=str(r['team_abbrev']);g=games.get(gid)
            if not g or tid not in (g['home'],g['away']):continue
            boxes[(gid,tid)]=clean({'shots':num(r.get('shots_on_goal')),'pp_goals':num(r.get('power_play_goals')),
               'saves':num(r.get('saves')),'pim':num(r.get('pim')),'hits':num(r.get('hits')),'blocks':num(r.get('blocked_shots'))})
    if advanced:
        from .events import enrich_hockey
        enrich_hockey(fetch,seasons,games,boxes)
    return teams,games,boxes

def collect(fetch,seasons,advanced=False,live=True):
    if SPORT=='nfl':return nfl(fetch,seasons,advanced)
    if SPORT in ('nba','cbb'):return basketball(fetch,seasons)
    if SPORT=='cfb':return college_football(fetch,seasons,advanced)
    if SPORT=='nhl':return hockey(fetch,seasons,advanced)
    return baseball(fetch,seasons,live)


def mlb_season_reference(fetch,seasons):
    """One low-volume official summary request for the current regular season.

    No player/game-log bulk fetch. Original MLB terms still apply to deployment.
    """
    current=datetime.now(NY).year
    if SPORT!='mlb' or current not in seasons:return []
    url=f'https://statsapi.mlb.com/api/v1/teams/stats?group=hitting,pitching&stats=season&season={current}&sportIds=1&gameType=R'
    obj=json.loads(fetch.get(url,ttl=3600).read_text());groups={}
    for group in obj.get('stats',[]):
        label=group.get('group',{}).get('displayName')
        if label not in ('hitting','pitching'):continue
        groups[label]={sid(x['team']['id']):x['stat'] for x in group.get('splits',[]) if str(x.get('season'))==str(current)}
    hitting=groups.get('hitting',{});pitching=groups.get('pitching',{})
    if len(hitting)!=30 or len(pitching)!=30:raise SourceError('Official MLB season summary does not contain all 30 teams')
    fields=('outs','earnedRuns','homeRuns','baseOnBalls','hitBatsmen','strikeOuts')
    valid=[s for s in pitching.values() if all(num(s.get(k)) is not None for k in fields)]
    outs=sum(num(s['outs']) for s in valid)
    constant=(27*sum(num(s['earnedRuns']) for s in valid)-3*sum(13*num(s['homeRuns'])+3*(num(s['baseOnBalls'])+num(s['hitBatsmen']))-2*num(s['strikeOuts']) for s in valid))/outs if outs else None
    result=[]
    def rate(s,a,b):
        x,y=num(s.get(a)),num(s.get(b));return 100*x/y if x is not None and y and y>0 else None
    for tid,s in hitting.items():
        d=pitching[tid];n=num(s.get('gamesPlayed'));np=num(d.get('gamesPlayed'))
        metrics={'avg':num(s.get('avg')),'obp':num(s.get('obp')),'slg':num(s.get('slg')),'ops':num(s.get('ops')),
         'hr':num(s.get('homeRuns'))/n if n else None,'k_rate':rate(s,'strikeOuts','plateAppearances'),'bb_rate':rate(s,'baseOnBalls','plateAppearances'),
         'era':num(d.get('era')),'whip':num(d.get('whip')),'pk_rate':rate(d,'strikeOuts','battersFaced'),'pbb_rate':rate(d,'baseOnBalls','battersFaced')}
        if constant is not None and num(d.get('outs')):
            metrics['fip']=3*(13*num(d['homeRuns'])+3*(num(d['baseOnBalls'])+num(d['hitBatsmen']))-2*num(d['strikeOuts']))/num(d['outs'])+constant
        observed=datetime.now(timezone.utc).isoformat()
        result.append({'season':current,'team_id':tid,'scope':'regular_season','source':url,'retrieved_at':observed,
           'payload':{'metrics':metrics,'hitting_games':int(n) if n else 0,'pitching_games':int(np) if np else 0,
            'scope_note':'Official MLB regular-season summary; not inferred game-log/rolling data.',
            'copyright':obj.get('copyright','Original MLB data rights apply.')}})
    return result
