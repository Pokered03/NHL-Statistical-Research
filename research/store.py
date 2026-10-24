"""Small indexed SQLite reads in the web process; atomic publishing by the worker."""
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get('RESEARCH_DB_PATH', ROOT / 'data' / 'research.sqlite'))
SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS teams(id TEXT PRIMARY KEY,name TEXT NOT NULL,division TEXT,conference TEXT);
CREATE TABLE IF NOT EXISTS team_seasons(season INTEGER NOT NULL,team_id TEXT NOT NULL REFERENCES teams(id),name TEXT NOT NULL,division TEXT,conference TEXT,PRIMARY KEY(season,team_id));
CREATE TABLE IF NOT EXISTS games(id TEXT PRIMARY KEY,season INTEGER NOT NULL,date TEXT NOT NULL,start TEXT,
 home TEXT NOT NULL REFERENCES teams(id),away TEXT NOT NULL REFERENCES teams(id),neutral INTEGER NOT NULL,
 status TEXT NOT NULL,home_score REAL,away_score REAL,venue TEXT,source TEXT NOT NULL,updated_at TEXT NOT NULL,
 CHECK(home<>away),CHECK(status IN ('scheduled','live','final','postponed','cancelled','suspended')),
 CHECK(status<>'final' OR (home_score IS NOT NULL AND away_score IS NOT NULL)));
CREATE INDEX IF NOT EXISTS games_date ON games(date,season);
CREATE INDEX IF NOT EXISTS games_home ON games(home,season,date);
CREATE INDEX IF NOT EXISTS games_away ON games(away,season,date);
CREATE TABLE IF NOT EXISTS boxes(game_id TEXT NOT NULL REFERENCES games(id),team_id TEXT NOT NULL REFERENCES teams(id),
 payload TEXT NOT NULL,PRIMARY KEY(game_id,team_id));
CREATE TABLE IF NOT EXISTS snapshots(season INTEGER NOT NULL,team_id TEXT NOT NULL REFERENCES teams(id),
 asof TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(season,team_id));
CREATE TABLE IF NOT EXISTS market_history(game_id TEXT PRIMARY KEY REFERENCES games(id),home_spread REAL,total_line REAL,source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS models(season INTEGER PRIMARY KEY,asof TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS team_context(season INTEGER NOT NULL,team_id TEXT NOT NULL REFERENCES teams(id),kind TEXT NOT NULL,asof TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(season,team_id,kind));
CREATE TABLE IF NOT EXISTS game_context(game_id TEXT PRIMARY KEY REFERENCES games(id),asof TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS season_reference(season INTEGER NOT NULL,team_id TEXT NOT NULL REFERENCES teams(id),scope TEXT NOT NULL,source TEXT NOT NULL,retrieved_at TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(season,team_id,scope));
'''

def connect(path=DB_PATH, readonly=True):
    path=Path(path)
    if readonly:
        c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        c=sqlite3.connect(path,timeout=30)
        c.executescript(SCHEMA)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA cache_size=-4096')
    c.execute('PRAGMA foreign_keys=ON')
    return c

def query(sql,args=(),path=DB_PATH):
    with connect(path) as c: return [dict(r) for r in c.execute(sql,args)]

def metadata(path=DB_PATH):
    return {r['key']:json.loads(r['payload']) for r in query('SELECT * FROM metadata',path=path)}

def teams(season,path=DB_PATH):
    return query('SELECT team_id AS id,name,division,conference FROM team_seasons WHERE season=? ORDER BY name',(season,),path)

def seasons(path=DB_PATH):
    return [r['season'] for r in query('SELECT DISTINCT season FROM games ORDER BY season DESC',path=path)]

def schedule(season,date,path=DB_PATH):
    return query('''SELECT g.*,h.name home_name,a.name away_name FROM games g JOIN teams h ON g.home=h.id
      JOIN teams a ON g.away=a.id WHERE g.season=? AND g.date=? ORDER BY g.start,g.id''',(season,date),path)

def snapshot(season,team,path=DB_PATH):
    rows=query('SELECT asof,payload FROM snapshots WHERE season=? AND team_id=?',(season,team),path)
    return {'asof':rows[0]['asof'],**json.loads(rows[0]['payload'])} if rows else None

def model(season,path=DB_PATH):
    r=query('SELECT asof,payload FROM models WHERE season=?',(season,),path)
    return {'asof':r[0]['asof'],**json.loads(r[0]['payload'])} if r else None

def recent_games(season,team,limit=10,path=DB_PATH):
    return query('''SELECT g.*,h.name home_name,a.name away_name FROM games g JOIN teams h ON g.home=h.id
    JOIN teams a ON g.away=a.id WHERE g.season=? AND (g.home=? OR g.away=?) AND g.status='final'
    ORDER BY g.date DESC,g.id DESC LIMIT ?''',(season,team,team,min(limit,20)),path)

def head_to_head(a,b,path=DB_PATH):
    return query('''SELECT g.*,h.name home_name,a.name away_name FROM games g JOIN teams h ON g.home=h.id
    JOIN teams a ON g.away=a.id WHERE ((g.home=? AND g.away=?) OR (g.home=? AND g.away=?))
    AND g.status='final' ORDER BY g.date DESC,g.id DESC LIMIT 10''',(a,b,b,a),path)


def team_context(season,team,path=DB_PATH):
    return [{'asof':r['asof'],**json.loads(r['payload'])} for r in query('SELECT asof,payload FROM team_context WHERE season=? AND team_id=?',(season,team),path)]

def game_context(gid,path=DB_PATH):
    rows=query('SELECT asof,payload FROM game_context WHERE game_id=?',(gid,),path)
    return {'asof':rows[0]['asof'],**json.loads(rows[0]['payload'])} if rows else None
