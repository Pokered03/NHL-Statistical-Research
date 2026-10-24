"""Historical-line research validation. No pricing requests and no betting execution."""
import math

def metrics(rows):
    if not rows:return {'n':0,'gate':False,'reason':'No verified historical lines.'}
    n=len(rows);brier=sum((r['p']-r['y'])**2 for r in rows)/n;ece=0.;bins=[]
    for bucket in range(10):
        subset=[r for r in rows if min(int(r['p']*10),9)==bucket]
        if subset:
            avg=sum(r['p'] for r in subset)/len(subset);obs=sum(r['y'] for r in subset)/len(subset)
            bins.append({'lower':bucket/10,'n':len(subset),'predicted':avg,'observed':obs});ece+=len(subset)/n*abs(avg-obs)
    categories={}
    for label,lo,hi in [('moderate',.55,.65),('strong',.65,1.00000001)]:
        subset=[r for r in rows if lo<=max(r['p'],1-r['p'])<hi]
        m=len(subset);wins=sum((r['p']>=.5)==bool(r['y']) for r in subset)
        if m:
            p=wins/m;z=1.96;lower=(p+z*z/(2*m)-z*math.sqrt(p*(1-p)/m+z*z/(4*m*m)))/(1+z*z/m)
        else:p=lower=None
        categories[label]={'n':m,'observed_selected_direction_rate':p,'wilson_95_lower':lower,'supported':bool(m>=50 and lower>.5)}
    return {'n':n,'brier':brier,'baseline_brier':.25,'ece':ece,'bins':bins,'gate':n>=200 and brier<.25 and ece<=.10,'categories':categories,
      'reason':'Gate: at least 200 held-out non-push line comparisons, ECE <=0.10, Brier <0.25. A category additionally needs 50 held-out cases and a Wilson lower bound above 50%. No prices/returns evaluated.'}

def evaluate(cal,test):
    errors={'spread':[r['actual_margin']-r['margin'] for r in cal], 'total':[r['actual_total']-r['total'] for r in cal]}
    report={}
    for kind,linekey in [('spread','home_spread'),('total','market_total')]:
        rows=[];pushes=0;lines=[]
        for r in test:
            line=r.get(linekey)
            if line is None:continue
            actual=r['actual_margin']+line if kind=='spread' else r['actual_total']-line
            if abs(actual)<1e-9:pushes+=1;continue
            projection=r['margin']+line if kind=='spread' else r['total']-line
            p=sum(projection+e>0 for e in errors[kind])/len(errors[kind])
            rows.append({'p':p,'y':int(actual>0)});lines.append(line)
        d=metrics(rows);d.update({'pushes_excluded':pushes,'source':'nflverse schedule historical closing line' if lines else None,'line_range':[min(lines),max(lines)] if lines else None})
        report[kind]=d
    return report
