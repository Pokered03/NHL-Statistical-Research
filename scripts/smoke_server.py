"""Verify this project's actual Streamlit HTTP server independently of AppTest."""
import json,os,socket,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
with tempfile.TemporaryFile() as log:
    p=subprocess.Popen([sys.executable,'-m','streamlit','run','app.py','--server.address=127.0.0.1',f'--server.port={port}'],cwd=root,stdout=log,stderr=log)
    t=time.perf_counter();result=None
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if p.poll() is not None:raise RuntimeError('Server exited before health check')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1) as r:
                    if r.read().decode()=='ok':break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Health check timed out')
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=3) as r:assert r.status==200
        result={'http_health':'ok','root_http_status':200,'seconds_to_health':time.perf_counter()-t,'actual_host_tested':False,'environment':'local isolated Streamlit process'}
        (root/'reports/server-smoke.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill();p.wait()
