"""Fail before publication if data integrity or minimum coverage is broken."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.store import connect,DB_PATH,metadata
from research.config import SPORT,EXPECTED_TEAMS
with connect() as c:
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    assert c.execute('SELECT COUNT(*) FROM games').fetchone()[0]>0
    assert not c.execute("SELECT id FROM games WHERE status='final' AND (home_score IS NULL OR away_score IS NULL)").fetchall()
    assert not c.execute('SELECT game_id,team_id,COUNT(*) n FROM boxes GROUP BY game_id,team_id HAVING n>1').fetchall()
    per=[dict(x) for x in c.execute('SELECT season,COUNT(*) games FROM games GROUP BY season')]
print(json.dumps({'sport':SPORT,'database_bytes':DB_PATH.stat().st_size,'seasons':per,'integrity':'ok'},indent=2))
