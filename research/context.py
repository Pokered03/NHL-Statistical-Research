"""Observed player roles and explicitly sourced probable starters. No injury inference."""
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from .sources import SDV,NY,SourceError,num,sid,truth,when,game
from .config import SPORT
from .events import batches

def basketball_roles(fetch,seasons,games,boxes):
    if SPORT not in ('nba','cbb'):return []
    repo,prefix=('hoopR-nba-data','nba') if SPORT=='nba' else ('hoopR-mbb-data','mbb')
    result=[]
    for year in seasons:
        gs=[g for g in games.values() if g['season']==year and g['status']=='final']
        if not gs:continue
        recent=defaultdict(list)
        for g in sorted(gs,key=lambda g:(g['date'],g['id'])):
            recent[g['home']].append(g['id']);recent[g['away']].append(g['id'])
        recent={t:set(ids[-6:]) for t,ids in recent.items()}
        wanted=['game_id','team_id','athlete_id','athlete_display_name','minutes','points','starter','field_goals_attempted','free_throws_attempted','turnovers']
        url=f'{SDV}{repo}/main/{prefix}/player_box/parquet/player_box_{year}.parquet'
        lines=defaultdict(list);totals={};seen=set()
        try:
            for r in batches(fetch,url,wanted,required=['game_id','team_id','athlete_id','minutes','points','starter']):
                gid,tid,pid=sid(r.get('game_id')),sid(r.get('team_id')),sid(r.get('athlete_id'));g=games.get(gid)
                if not g or g['status']!='final' or g['season']!=year or tid not in (g['home'],g['away']) or pid is None:continue
                key=(gid,tid,pid)
                if key in seen:continue
                seen.add(key);mins=num(r.get('minutes'));pts=num(r.get('points'));starter=r.get('starter')
                if pts is None and (mins is None or mins==0) and not truth(starter):continue
                z=totals.setdefault((gid,tid),{'points':0.,'bench':0.,'starters':0,'missing':False})
                if pts is None or starter is None:z['missing']=True
                else:z['points']+=pts;z['starters']+=int(truth(starter));z['bench']+=0. if truth(starter) else pts
                if gid in recent.get(tid,set()):
                    lines[(tid,gid)].append({'player_id':pid,'name':str(r.get('athlete_display_name') or pid),'minutes':mins,'points':pts,'reported_starter':truth(starter),
                        'endings':(num(r['field_goals_attempted'])+.44*num(r['free_throws_attempted'])+num(r['turnovers'])) if all(num(r.get(k)) is not None for k in ('field_goals_attempted','free_throws_attempted','turnovers')) else None})
        except SourceError as exc:
            fetch.log.append({'quality_event':'Player-role source unavailable','season':year,'reason':str(exc)});continue
        valid=set()
        for (gid,tid),z in totals.items():
            g=games[gid];score=g['home_score'] if tid==g['home'] else g['away_score']
            if not z['missing'] and z['starters']==5 and abs(z['points']-score)<.01:
                boxes.setdefault((gid,tid),{})['bench']=z['bench'];valid.add((tid,gid))
        for tid,gids in recent.items():
            ordered=sorted([gid for gid in gids if (tid,gid) in valid],key=lambda gid:(games[gid]['date'],gid),reverse=True)
            if not ordered:continue
            latest=ordered[0];previous=ordered[1] if len(ordered)>1 else None
            starters=[x['name'] for x in lines[(tid,latest)] if x['reported_starter']]
            prior=[x['player_id'] for x in lines[(tid,previous)] if x['reported_starter']] if previous else []
            latest_ids=[x['player_id'] for x in lines[(tid,latest)] if x['reported_starter']]
            players=defaultdict(list)
            for gid in ordered[:5]:
                for row in lines[(tid,gid)]:
                    if row['minutes'] is not None:players[row['player_id']].append(row)
            ending_rows=[x for records in players.values() for x in records]
            endings=sum(x['endings'] for x in ending_rows) if all(x['endings'] is not None for x in ending_rows) else None
            rotation=[]
            for pid,records in players.items():
                rotation.append({'Player':records[0]['name'],'Recorded appearances':len(records),'Minutes / recorded appearance':round(sum(r['minutes'] for r in records)/len(records),1),
                  'Reported starts':sum(r['reported_starter'] for r in records),'Recorded offensive-ending share':round(100*sum(r['endings'] for r in records)/endings,1) if endings is not None and endings>0 else None})
            rotation.sort(key=lambda r:r['Minutes / recorded appearance'],reverse=True)
            result.append({'season':year,'team_id':tid,'kind':'observed_rotation','asof':datetime.now(timezone.utc).isoformat(),
              'payload':{'source':url,'last_observed_game':games[latest]['date'],'reported_starters':starters,
                'starters_changed_from_previous':len(set(latest_ids)-set(prior)) if previous else None,'rotation':rotation[:10],
                'note':'Observed completed-game roles only. Not a live injury report or next-game lineup confirmation. Provider active/DNP/reason flags are not trusted; positive minutes and score/role reconciliation are used. Offensive-ending share is a descriptive proxy, not official usage rate. No forecast adjustment is applied.'}})
    return result

def mlb_upcoming_context(fetch,seasons,games,teams):
    if SPORT!='mlb':return
    import json
    from urllib.parse import urlencode
    now=datetime.now(NY);current=now.year
    if current not in seasons:return
    url='https://statsapi.mlb.com/api/v1/schedule?'+urlencode({'sportId':1,'startDate':str(now.date()-timedelta(days=2)),'endDate':str(now.date()+timedelta(days=7)),'hydrate':'probablePitcher'})
    try:obj=json.loads(fetch.get(url,ttl=1800).read_text())
    except SourceError as exc:fetch.log.append({'quality_event':'Current MLB schedule/probable source unavailable','reason':str(exc)});return
    pitchers=set()
    for day in obj.get('dates',[]):
        for row in day.get('games',[]):
            from .sources import status
            h,a=row['teams']['home'],row['teams']['away'];hid,aid=sid(h['team']['id']),sid(a['team']['id'])
            if hid not in teams or aid not in teams or row.get('gameType') not in ('R','F','D','L','W'):continue
            d,ts=when(row.get('gameDate'));st=status(row.get('status',{}).get('detailedState'))
            g=game('mlb-'+str(row['gamePk']),current,hid,aid,d,ts,h.get('score'),a.get('score'),st,False,row.get('venue',{}).get('name',''))
            context={'source':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'probable_pitchers':{}}
            for side,team in [('home',h),('away',a)]:
                probable=team.get('probablePitcher')
                if probable:
                    pid=sid(probable['id']);pitchers.add(pid);context['probable_pitchers'][side]={'id':pid,'name':probable['fullName'],'status':'PROBABLE — not confirmed'}
            g['_context']=context
            games[g['id']]=g
    if not pitchers:return
    url='https://statsapi.mlb.com/api/v1/people?'+urlencode({'personIds':','.join(sorted(pitchers)),'hydrate':f'stats(group=[pitching],type=[season],season={current})'})
    try:people=json.loads(fetch.get(url,ttl=3600).read_text()).get('people',[])
    except SourceError as exc:fetch.log.append({'quality_event':'Probable pitcher season stats unavailable','reason':str(exc)});return
    stats={}
    for person in people:
        p={'Throws':person.get('pitchHand',{}).get('description'),'Season':current}
        for group in person.get('stats',[]):
            if group.get('group',{}).get('displayName')!='pitching':continue
            splits=group.get('splits',[])
            aggregate=[s for s in splits if not s.get('team')]
            eligible_splits=aggregate or (splits if len(splits)==1 else [])
            for split in eligible_splits:
                if str(split.get('season'))!=str(current):continue
                s=split.get('stat',{});p.update({key:s.get(field) for key,field in [('ERA','era'),('WHIP','whip'),('IP','inningsPitched'),('K/9','strikeoutsPer9Inn'),('BB/9','walksPer9Inn'),('Starts','gamesStarted')]})
                bf=num(s.get('battersFaced'))
                if bf:p['K%']=round(100*(num(s.get('strikeOuts')) or 0)/bf,1);p['BB%']=round(100*(num(s.get('baseOnBalls')) or 0)/bf,1)
                break
        stats[sid(person['id'])]=p
    for g in games.values():
        if '_context' not in g:continue
        for p in g['_context']['probable_pitchers'].values():p['season_stats']=stats.get(p['id'],{});p['stats_source']=url
