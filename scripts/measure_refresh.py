import json,resource,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.config import SPORT,ACTIVE_SEASON
root=Path(__file__).resolve().parents[1]
cmd=[sys.executable,'-m','research.pipeline','--seasons',str(ACTIVE_SEASON)]
if SPORT in ('nfl','nhl','cfb'):cmd.append('--advanced')
t=time.perf_counter();run=subprocess.run(cmd,cwd=root,capture_output=True,text=True)
r={'sport':SPORT,'operation':'Active-season cached free-data refresh plus full chronological validation',
 'seconds':time.perf_counter()-t,'worker_peak_rss_mib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024,
 'exit_code':run.returncode,'target_peak_rss_mib':650,'hosting_environment':False}
(root/'reports').mkdir(exist_ok=True);(root/'reports/refresh-performance.json').write_text(json.dumps(r,indent=2))
(root/'reports/last-refresh.log').write_text(run.stdout+run.stderr)
print(json.dumps(r,indent=2))
if run.returncode:raise SystemExit(run.returncode)
