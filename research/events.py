"""Column-bounded event aggregation in the data worker, never the web process."""
from collections import defaultdict
from .sources import SDV,SourceError,sid,num,truth

def batches(fetch,url,wanted,required=()):
    import pyarrow.parquet as pq
    f=pq.ParquetFile(fetch.get(url,ttl=3600))
    if not set(required).issubset(f.schema_arrow.names):raise SourceError('Required event columns missing; advanced statistics withheld')
    columns=[c for c in wanted if c in f.schema_arrow.names]
    for batch in f.iter_batches(batch_size=4096,columns=columns):yield from batch.to_pylist()

def aggregate_hockey(rows,games):
    agg={};ended=set();seen=set()
    keys=['attempts','unblocked','faceoff_wins','faceoff_total','xg_sum','xg_observed','xg_attempts','hdc','goalie_xg','goalie_observed','goalie_attempts','goalie_goals','on_target']
    def team(gid,tid):return agg.setdefault((gid,tid),{k:0. for k in keys})
    for r in rows:
        gid=sid(r.get('game_id'));g=games.get(gid)
        if not g or g['status']!='final':continue
        event=str(r.get('event_type','')).upper()
        if event=='GAME_END':ended.add(gid)
        if str(r.get('period_type','')).upper()=='SHOOTOUT':continue
        tid=r.get('event_team_abbr')
        if tid not in (g['home'],g['away']):continue
        token=r.get('event_idx') if r.get('event_idx') is not None else r.get('event_id')
        if token is not None:
            key=(gid,str(token))
            if key in seen:continue
            seen.add(key)
        opponent=g['away'] if tid==g['home'] else g['home']
        if event=='BLOCKED_SHOT':tid,opponent=opponent,tid  # event owner is the blocker in this publisher schema
        p=team(gid,tid);q=team(gid,opponent)
        if event=='FACEOFF':p['faceoff_wins']+=1;p['faceoff_total']+=1;q['faceoff_total']+=1
        if event in ('SHOT','GOAL','MISSED_SHOT','BLOCKED_SHOT'):p['attempts']+=1
        if event in ('SHOT','GOAL'):p['on_target']+=1
        if event in ('SHOT','GOAL','MISSED_SHOT'):
            p['unblocked']+=1;p['xg_attempts']+=1;x=num(r.get('xg'))
            if x is not None and 0<=x<=1:p['xg_sum']+=x;p['xg_observed']+=1;p['hdc']+=int(x>=.20)
            if event in ('SHOT','GOAL') and not truth(r.get('empty_net')):
                p['goalie_attempts']+=1;p['goalie_goals']+=int(event=='GOAL')
                if x is not None and 0<=x<=1:p['goalie_xg']+=x;p['goalie_observed']+=1
    result={}
    for (gid,tid),p in agg.items():
        if gid not in ended:continue
        g=games[gid];opp=g['away'] if tid==g['home'] else g['home'];q=agg[(gid,opp)]
        out={k:p[k] for k in ('attempts','unblocked','faceoff_wins','faceoff_total')}
        out['_on_target']=p['on_target'];out['modeled_xg']=p['xg_sum'];out['modeled_attempts']=p['xg_observed']
        if p['xg_attempts']>0 and p['xg_observed']==p['xg_attempts']:out.update(xg=p['xg_sum'],hdc=p['hdc'])
        if q['goalie_attempts']>0 and q['goalie_observed']==q['goalie_attempts']:out['gsax']=q['goalie_xg']-q['goalie_goals']
        result[(gid,tid)]=out
    return result

def enrich_hockey(fetch,seasons,games,boxes):
    wanted=['game_id','event_type','event_team_abbr','period_type','xg','empty_net','event_idx','event_id']
    for year in seasons:
        url=f'{SDV}fastRhockey-nhl-data/main/nhl/pbp/parquet/play_by_play_{year}.parquet'
        try:stats=aggregate_hockey(batches(fetch,url,wanted),games)
        except SourceError as exc:
            fetch.log.append({'quality_event':'NHL event data unavailable','season':year,'reason':str(exc)});continue
        invalid=set()
        for (gid,tid),p in stats.items():
            observed=boxes.get((gid,tid),{}).get('shots')
            if observed is None or p['_on_target']!=observed:invalid.add(gid)
        for key,p in stats.items():
            if key[0] not in invalid:
                p.pop('_on_target',None);boxes.setdefault(key,{}).update(p)
        if invalid:fetch.log.append({'quality_event':'NHL incomplete shot-count event histories excluded','season':year,'games':len(invalid)})
    return boxes

def aggregate_college(rows,games):
    agg={};ended=set();halves={};rz={};seen=set();drive_known=set()
    keys=['epa_sum','epa_n','success','pass_comp','pass_att','pass_int','pass_td','rush_td','sacks_allowed','third_made','third_att','explosive','explosive_att','line_yards','line_rush_n','qb_disruption','dropbacks']
    def team(gid,tid):return agg.setdefault((gid,tid),{k:0. for k in keys})
    for r in rows:
        gid=sid(r.get('game_id'));g=games.get(gid)
        if not g or g['status']!='final':continue
        period=num(r.get('period'));hs=num(r.get('homeScore'));aws=num(r.get('awayScore'))
        if truth(r.get('end_of_half')):
            if period==2 and hs is not None and aws is not None:halves[gid]=(hs,aws)
            if period is not None and period>=4 and hs==g['home_score'] and aws==g['away_score']:ended.add(gid)
        tid=sid(r.get('pos_team_id'))
        if tid not in (g['home'],g['away']):continue
        token=r.get('id') if r.get('id') is not None else r.get('game_play_number')
        if token is not None:
            k=(gid,str(token))
            if k in seen:continue
            seen.add(k)
        if not truth(r.get('scrimmage_play')) or truth(r.get('penalty_no_play')):continue
        p=team(gid,tid)
        def add(key,v):
            v=num(v)
            if v is None:return
            p[key]=p.get(key,0)+v
            if period in (1,2):p['half_'+key]=p.get('half_'+key,0)+v
        e=num(r.get('EPA_scrimmage'))
        if e is None:e=num(r.get('EPA'))
        if e is not None:add('epa_sum',e);add('epa_n',1);add('success',e>0)
        rush=truth(r.get('rush'));passing=truth(r.get('pass'));sack=truth(r.get('sack'))
        if truth(r.get('pass_attempt')) and not sack:
            add('pass_att',1);add('pass_comp',truth(r.get('completion')));add('pass_int',truth(r.get('int')))
        add('pass_td',truth(r.get('pass_td')));add('rush_td',truth(r.get('rush_td')));add('sacks_allowed',sack)
        if passing or sack or truth(r.get('pass_attempt')):
            add('dropbacks',1);add('qb_disruption',sack or truth(r.get('qb_hurry')))
        if num(r.get('down'))==3:
            add('third_att',1);add('third_made',truth(r.get('first_down_earned')) or truth(r.get('pass_td')) or truth(r.get('rush_td')))
        y=num(r.get('yds_rushed')) if rush else num(r.get('yds_receiving')) if truth(r.get('completion')) else 0.
        add('explosive_att',1);add('explosive',y is not None and ((rush and y>=10) or (not rush and y>=20)))
        ly=num(r.get('line_yards'))
        if rush and ly is not None:add('line_yards',ly);add('line_rush_n',1)
        yd=num(r.get('start.yardsToEndzone'));drive=r.get('drive.id')
        if drive is not None:drive_known.add((gid,tid))
        if yd is not None and yd<=20 and drive is not None:
            z=rz.setdefault((gid,tid),{'trips':set(),'td':set()});z['trips'].add(str(drive))
            if str(r.get('drive.result')).upper()=='TD':z['td'].add(str(drive))
    result={}
    for key,p in agg.items():
        gid,tid=key
        if gid not in ended:continue
        if key in rz:p['rz_trips']=len(rz[key]['trips']);p['rz_td']=len(rz[key]['td'])
        elif key in drive_known:p['rz_trips']=p['rz_td']=0.
        if gid in halves:p['half_points']=halves[gid][0 if tid==games[gid]['home'] else 1]
        result[key]=p
    return result

def enrich_college(fetch,seasons,games,boxes):
    wanted=['game_id','id','game_play_number','pos_team_id','period','homeScore','awayScore','end_of_half','scrimmage_play','penalty_no_play','EPA_scrimmage','EPA','rush','pass','sack','pass_attempt','completion','int','pass_td','rush_td','qb_hurry','down','first_down_earned','yds_rushed','yds_receiving','line_yards','start.yardsToEndzone','drive.id','drive.result']
    for year in seasons:
        url=f'{SDV}cfbfastR-cfb-data/main/cfb/pbp/parquet/play_by_play_{year}.parquet'
        try:stats=aggregate_college(batches(fetch,url,wanted,required=['game_id','pos_team_id','period','end_of_half','scrimmage_play','pass_attempt','completion','int','pass_td','rush_td','sack','EPA']),games)
        except SourceError as exc:
            fetch.log.append({'quality_event':'College event data unavailable','season':year,'reason':str(exc)});continue
        for key,p in stats.items():boxes.setdefault(key,{}).update(p)
    return boxes
