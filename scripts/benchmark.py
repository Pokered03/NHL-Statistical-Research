"""Fresh-process AppTest benchmark; no hosting-limit claim is made."""
import json,os,resource,sys,time,statistics,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from research import store
from research.config import SPORT
root=Path(__file__).resolve().parents[1];t=time.perf_counter()
at=AppTest.from_file(str(root/'app.py'),default_timeout=30).run();cold=time.perf_counter()-t
if at.exception:raise RuntimeError(str(at.exception))
prepared=store.query('SELECT DISTINCT season FROM snapshots ORDER BY season DESC')
if prepared and at.selectbox[0].value!=prepared[0]['season']:at.selectbox[0].set_value(prepared[0]['season']).run()
t=time.perf_counter();at.radio[0].set_value('Manual teams').run();first_matchup=time.perf_counter()-t
if at.exception:raise RuntimeError(str(at.exception))
choices=[r['id'] for r in store.teams(at.selectbox[0].value)];times=[]
rss_samples=[]
for index in range(64):
    # Set the stable team ID, rather than the formatted display label.
    t=time.perf_counter();at.selectbox[1].set_value(choices[index%len(choices)]).run();times.append(time.perf_counter()-t)
    if index+1 in (8,16,32,64):rss_samples.append({'switch':index+1,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024})
    if at.exception:raise RuntimeError(str(at.exception))
peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
result={'sport':SPORT,'environment':'local Streamlit AppTest; not deployed hosting','cold_render_seconds':cold,
 'initial_matchup_render_seconds':first_matchup,'switch_p95_seconds':sorted(times)[max(0,math.ceil(len(times)*.95)-1)] if times else None,
 'switches':len(times),'rss_samples':rss_samples,'peak_rss_mib':peak,'db_mib':store.DB_PATH.stat().st_size/1024**2,
 'targets':{'cold_render_seconds':10,'switch_p95_seconds':2,'peak_rss_mib':350},
 'actual_host_limits_tested':False}
result['local_targets_pass']=cold<10 and peak<350 and (not times or max(times)<2)
(root/'reports').mkdir(exist_ok=True);(root/'reports/performance.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
