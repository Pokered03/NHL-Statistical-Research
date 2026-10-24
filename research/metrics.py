"""Ratios aggregate numerators/denominators, never averages of percentages."""
from dataclasses import dataclass
import math
from .config import SPORT

@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    section: str
    direction: int  # +1 higher favorable; -1 lower favorable; 0 descriptive
    numerator: tuple
    denominator: tuple=()
    scale: float=1.0
    unit: str=''
    note: str=''

    def value(self,rows):
        if not rows: return None,0
        if self.key=='passer_rating':
            valid=[r for r in rows if all(r.get(k) is not None for k in ('pass_comp','pass_att','pass_yards','pass_td','pass_int'))]
            if not valid:return None,0
            vals={k:sum(r[k] for r in valid) for k in ('pass_comp','pass_att','pass_yards','pass_td','pass_int')};a=vals['pass_att']
            if a<=0:return None,len(valid)
            if SPORT=='cfb':v=(8.4*vals['pass_yards']+330*vals['pass_td']+100*vals['pass_comp']-200*vals['pass_int'])/a
            else:
                clamp=lambda x:max(0,min(2.375,x))
                v=100/6*(clamp((vals['pass_comp']/a-.3)*5)+clamp((vals['pass_yards']/a-3)*.25)+clamp(vals['pass_td']/a*20)+clamp(2.375-vals['pass_int']/a*25))
            return v,len(valid)
        if self.key=='fip':
            valid=[r for r in rows if all(r.get(k) is not None for k in ('fip_num','outs','fip_constant'))]
            outs=sum(r['outs'] for r in valid)
            return ((sum(r['fip_num'] for r in valid)*3/outs+valid[0]['fip_constant']) if outs>0 else None),len(valid)
        if self.key=='ops':
            ob=BY_KEY['obp'].value(rows);sl=BY_KEY['slg'].value(rows)
            return (ob[0]+sl[0] if ob[0] is not None and sl[0] is not None else None),min(ob[1],sl[1])
        valid=[r for r in rows if all(r.get(k) is not None and math.isfinite(r[k]) for k,_ in self.numerator+self.denominator)]
        if not valid:return None,0
        n=sum(sum(r[k]*w for k,w in self.numerator) for r in valid)
        d=sum(sum(r[k]*w for k,w in self.denominator) for r in valid) if self.denominator else len(valid)
        return (self.scale*n/d if d>0 else None),len(valid)

def per(key,label,section,direction=1,primitive=None,note=''):
    return Metric(key,label,section,direction,((primitive or key,1),),note=note)
def ratio(key,label,section,num,den,scale=100,direction=1,note=''):
    return Metric(key,label,section,direction,tuple(num),tuple(den),scale,'%' if scale==100 else '',note)

BASE=[per('points','Points scored / game','Offense'),per('allowed','Points allowed / game','Defense',-1),
      per('margin','Scoring margin / game','Situational'),per('rest','Days between game dates','Situational',0,note='Calendar days, including the game day; 1 means back-to-back.'),
      per('win','Win rate','Situational')]
FOOTBALL=[ratio('line_yards_rate','Source line yards / rush','Offense',[('line_yards',1)],[('line_rush_n',1)],1,note='Publisher rushing-line proxy; not a proprietary offensive-line grade.'),ratio('opp_line_yards_rate','Opponent line yards / rush','Defense',[('opp_line_yards',1)],[('opp_line_rush_n',1)],1,-1),ratio('recorded_disruption','Recorded QB disruption allowed','Offense',[('qb_disruption',1)],[('dropbacks',1)],100,-1,note='Recorded hurry-or-sack flags; not complete tracking pressure rate.'),ratio('opp_recorded_disruption','Recorded defensive QB disruption','Defense',[('opp_qb_disruption',1)],[('opp_dropbacks',1)],100,1,note='Provider-recorded hurries or sacks divided by observed dropbacks.'),per('pass_yards','Passing yards / game','Offense'),per('rush_yards','Rushing yards / game','Offense'),
 per('pass_td','Pass TD / game','Offense'),per('rush_td','Rush TD / game','Offense'),
 ratio('ypp','Yards / play','Offense',[('yards',1)],[('plays',1)],1),
 ratio('epa','EPA / play','Offense',[('epa_sum',1)],[('epa_n',1)],1),
 ratio('success','Positive-EPA plays','Offense',[('success',1)],[('epa_n',1)]),
 ratio('explosive','Explosive play rate','Offense',[('explosive',1)],[('explosive_att',1)],note='Pass gain >=20 yards or rush gain >=10 yards.'),
 ratio('third','Third-down conversions','Situational',[('third_made',1)],[('third_att',1)]),
 ratio('rz','Red-zone TD efficiency','Situational',[('rz_td',1)],[('rz_trips',1)]),
 per('sacks_allowed','Sacks allowed / game','Offense',-1),per('sacks','Defensive sacks / game','Defense'),
 per('opp_pass_yards','Passing yards allowed / game','Defense',-1),per('opp_rush_yards','Rushing yards allowed / game','Defense',-1),
 ratio('opp_ypp','Yards allowed / play','Defense',[('opp_yards',1)],[('opp_plays',1)],1,-1),
 ratio('opp_epa','EPA allowed / play','Defense',[('opp_epa_sum',1)],[('opp_epa_n',1)],1,-1),
 ratio('opp_success','Positive-EPA plays allowed','Defense',[('opp_success',1)],[('opp_epa_n',1)],100,-1),
 ratio('opp_third','Third-down conversions allowed','Situational',[('opp_third_made',1)],[('opp_third_att',1)],100,-1),
 per('turnover_margin','Turnover margin / game','Situational'),per('penalty_yards','Penalty yards / game','Situational',-1),
 per('plays','Offensive snaps / game','Situational',0),
 per('pressure_rate','Pressure rate [tracking source needed]','Defense'),
 per('passer_rating','Team passer rating','Offense',note='All team passers combined; not a starting-QB forecast.'),
 per('line_grade','Offensive line grade [licensed source needed]','Offense')]
BASKETBALL=[per('adjusted_ortg','Adjusted offense / 100 poss.','Offense',note='Season-only regularized box-score scoring model; not a proprietary efficiency rating.'),per('adjusted_drtg','Adjusted defense / 100 poss.','Defense',-1,note='Season-only regularized opponent-adjusted scoring efficiency.'),ratio('ortg','Offensive rating / 100 poss.','Offense',[('points',1)],[('poss',1)],100,note='Box-score possession estimate; includes overtime.'),
 ratio('drtg','Defensive rating / 100 poss.','Defense',[('allowed',1)],[('poss',1)],100,-1),
 ratio('netrtg','Net rating / 100 poss.','Situational',[('points',1),('allowed',-1)],[('poss',1)],100),
 per('poss','Possessions / game (OT included)','Situational',0),
 ratio('efg','Effective FG percentage','Offense',[('fgm',1),('fg3m',.5)],[('fga',1)]),
 ratio('ts','True shooting percentage','Offense',[('points',1)],[('fga',2),('fta',.88)]),
 ratio('three','Three-point percentage','Offense',[('fg3m',1)],[('fg3a',1)]),
 ratio('ftr','Free-throw attempts / FGA','Offense',[('fta',1)],[('fga',1)],1),
 ratio('orb','Offensive rebound percentage','Offense',[('oreb',1)],[('oreb',1),('opp_dreb',1)]),
 ratio('drb','Defensive rebound percentage','Defense',[('dreb',1)],[('dreb',1),('opp_oreb',1)]),
 ratio('tovrate','Turnovers / 100 possessions','Offense',[('tov',1)],[('poss',1)],100,-1),
 per('assists','Assists / game','Offense'),per('paint','Paint points / game','Offense'),per('blocks','Blocks / game','Defense'),
 per('steals','Steals / game','Defense'),ratio('opp_efg','Opponent effective FG percentage','Defense',[('opp_fgm',1),('opp_fg3m',.5)],[('opp_fga',1)],100,-1),
 per('bench','Bench points [player roles needed]','Offense'),per('lineup','Starting lineup continuity [unavailable]','Situational',0)]
BASEBALL=[ratio('avg','Batting average','Offense',[('hits',1)],[('ab',1)],1),
 ratio('obp','On-base percentage','Offense',[('hits',1),('bb',1),('hbp',1)],[('ab',1),('bb',1),('hbp',1),('sf',1)],1),
 ratio('slg','Slugging percentage','Offense',[('hits',1),('doubles',1),('triples',2),('hr',3)],[('ab',1)],1),
 per('ops','On-base plus slugging','Offense'),per('hr','Home runs / game','Offense'),
 ratio('k_rate','Batting strikeouts / PA','Offense',[('so',1)],[('ab',1),('bb',1),('hbp',1),('sf',1),('sh',1)],100,-1),
 ratio('bb_rate','Batting walks / PA','Offense',[('bb',1)],[('ab',1),('bb',1),('hbp',1),('sf',1),('sh',1)]),
 ratio('era','Team ERA','Defense',[('earned_runs',27)],[('outs',1)],1,-1),
 ratio('whip','Team WHIP','Defense',[('opp_hits',3),('opp_bb',3)],[('outs',1)],1,-1),
 ratio('pk_rate','Pitching strikeouts / PA','Defense',[('opp_so',1)],[('opp_ab',1),('opp_bb',1),('opp_hbp',1),('opp_sf',1),('opp_sh',1)]),
 ratio('pbb_rate','Pitching walks / PA','Defense',[('opp_bb',1)],[('opp_ab',1),('opp_bb',1),('opp_hbp',1),('opp_sf',1),('opp_sh',1)],100,-1),
 per('starter_era','Starting pitcher ERA [not yet integrated]','Defense',-1),per('fip','Team FIP (season constant)','Defense',-1),
 per('xfip','xFIP [fly-ball data needed]','Defense',-1),per('bullpen_era','Bullpen ERA [pitcher roles needed]','Defense',-1),
 per('bullpen_workload','Bullpen pitches last 3 days [unavailable]','Situational',-1),
 per('wrc_plus','wRC+ [verified source needed]','Offense'),per('xwoba','Statcast xwOBA [not yet integrated]','Offense'),
 per('park_factor','Ballpark run factor [not yet integrated]','Situational',0)]
HOCKEY=[ratio('xg_per_attempt','xG / modeled unblocked attempt','Offense',[('modeled_xg',1)],[('modeled_attempts',1)],1,note='Only shots with observed model values; not full expected-goal totals.'),per('shots','Shots on goal / game','Offense'),per('opp_shots','Shots allowed / game','Defense',-1),
 ratio('shooting','Shooting percentage','Offense',[('actual_goals',1)],[('shots',1)]),
 ratio('save','Team save percentage','Defense',[('saves',1)],[('opp_shots',1)]),
 ratio('powerplay','Power-play efficiency','Offense',[('pp_goals',1)],[('pp_opps',1)]),
 ratio('penaltykill','Penalty-kill efficiency','Defense',[('opp_pp_opps',1),('opp_pp_goals',-1)],[('opp_pp_opps',1)]),
 ratio('faceoff','Faceoff wins','Situational',[('faceoff_wins',1)],[('faceoff_total',1)]),
 per('xg','Observed expected goals / game','Offense',note='Publisher pre-shot xG; only games with complete unblocked-shot xG are included.'),per('opp_xg','Expected goals allowed / game','Defense',-1,note='Publisher model estimates, not observed goal outcomes.'),
 per('hdc','Shots with xG ≥ 0.20 / game','Offense',note='Explicit research definition; not a vendor high-danger chance label.'),ratio('corsi','Corsi share (all strengths)','Situational',[('attempts',1)],[('attempts',1),('opp_attempts',1)],note='Shot attempts including blocks; shootouts excluded. Block-owner events attributed to shooter.'),
 ratio('fenwick','Fenwick share (all strengths)','Situational',[('unblocked',1)],[('unblocked',1),('opp_unblocked',1)],note='Unblocked attempts; shootouts excluded.'),per('gsax','Team goalie pre-shot GSAx / game','Defense',note='Opponent on-target pre-shot xG minus goals; empty-net and shootout attempts excluded. Aggregates all goalies, not a starter prediction.')]
METRICS=BASE+({'nfl':FOOTBALL,'cfb':FOOTBALL,'nba':BASKETBALL,'cbb':BASKETBALL,'mlb':BASEBALL,'nhl':HOCKEY}[SPORT])
BY_KEY={m.key:m for m in METRICS}

def color(rank,pop):
    if rank is None or not pop:return 'missing'
    q=(rank-1)/max(pop-1,1)
    return 'good' if q<=1/3 else 'average' if q<=2/3 else 'poor'

def advantage(a,b,direction):
    if a is None or b is None or not direction:return '—'
    if math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6):return 'EVEN'
    return 'A' if (a-b)*direction>0 else 'B'
