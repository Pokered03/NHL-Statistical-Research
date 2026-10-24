import pytest
from research.events import aggregate_hockey,aggregate_college

def game():return {'g':{'id':'g','home':'H','away':'A','status':'final','home_score':3.,'away_score':2.}}

def test_blocked_shot_attributed_to_shooter_and_faceoff_winner():
    rows=[{'game_id':'g','event_type':'BLOCKED_SHOT','event_team_abbr':'H','event_idx':1,'period_type':'REGULAR'},
      {'game_id':'g','event_type':'FACEOFF','event_team_abbr':'A','event_idx':2,'period_type':'REGULAR'},
      {'game_id':'g','event_type':'SHOT','event_team_abbr':'A','event_idx':3,'period_type':'REGULAR','xg':.3,'empty_net':False},
      {'game_id':'g','event_type':'GOAL','event_team_abbr':'H','event_idx':4,'period_type':'REGULAR','xg':.1,'empty_net':False},
      {'game_id':'g','event_type':'GAME_END','event_idx':5}]
    r=aggregate_hockey(rows,game())
    assert r[('g','A')]['attempts']==2
    assert r[('g','H')]['attempts']==1
    assert r[('g','A')]['faceoff_wins']==1
    assert r[('g','H')]['faceoff_total']==1
    assert r[('g','A')]['hdc']==1
    assert r[('g','H')]['gsax']==pytest.approx(.3)
    assert r[('g','A')]['gsax']==pytest.approx(-.9)

def test_hockey_missing_xg_not_zero_and_shootout_excluded():
    rows=[{'game_id':'g','event_type':'SHOT','event_team_abbr':'A','event_idx':1,'period_type':'REGULAR','xg':None},
      {'game_id':'g','event_type':'GOAL','event_team_abbr':'H','event_idx':2,'period_type':'SHOOTOUT','xg':.5},
      {'game_id':'g','event_type':'GAME_END','event_idx':3}]
    r=aggregate_hockey(rows,game())
    assert 'xg' not in r[('g','A')]
    assert r[('g','H')]['attempts']==0
    assert 'gsax' not in r[('g','H')]
    assert aggregate_hockey(rows[:-1],game())=={}

def test_hockey_duplicate_event_not_double_counted():
    shot={'game_id':'g','event_type':'SHOT','event_team_abbr':'A','event_idx':1,'period_type':'REGULAR','xg':.2}
    r=aggregate_hockey([shot,shot,{'game_id':'g','event_type':'GAME_END'}],game())
    assert r[('g','A')]['attempts']==1

def test_college_completed_game_epa_and_half_scope():
    rows=[{'game_id':'g','id':1,'pos_team_id':'A','period':2,'homeScore':0,'awayScore':2,'end_of_half':True,'scrimmage_play':True,'EPA':1.,'rush':True,'rush_td':False,'yds_rushed':12,'line_yards':7,'down':3,'first_down_earned':True,'drive.id':'d','drive.result':'FG','start.yardsToEndzone':15},
      {'game_id':'g','id':2,'pos_team_id':'A','period':4,'homeScore':3,'awayScore':2,'end_of_half':True,'scrimmage_play':True,'EPA':-.5,'pass':True,'pass_attempt':True,'completion':False,'down':1}]
    r=aggregate_college(rows,game())[('g','A')]
    assert r['epa_sum']==.5 and r['epa_n']==2
    assert r['half_epa_sum']==1
    assert r['half_points']==2
    assert r['third_att']==1 and r['third_made']==1
    assert r['line_yards']==7 and r['line_rush_n']==1
    assert r['explosive']==1 and r['explosive_att']==2
    assert r['rz_trips']==1 and r['rz_td']==0
    assert aggregate_college(rows[:-1],game())=={}

def test_college_unknown_drive_not_fabricated():
    row={'game_id':'g','id':1,'pos_team_id':'A','period':4,'homeScore':3,'awayScore':2,'end_of_half':True,'scrimmage_play':True,'EPA':0.}
    r=aggregate_college([row],game())[('g','A')]
    assert 'rz_trips' not in r
