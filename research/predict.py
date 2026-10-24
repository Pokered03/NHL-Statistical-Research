"""Lightweight online model evaluation: no NumPy, SciPy, fitting, or network."""
import math
from statistics import NormalDist
from .config import MIN_TEAM_GAMES

def scores(m,home,away,neutral=False):
    if not m or home==away:return None
    idx={t:i for i,t in enumerate(m['teams'])}
    if home not in idx or away not in idx:return None
    b=m['beta'];n=len(idx);ha=0 if neutral else b[1]
    h=b[0]+ha+b[2+idx[home]]+b[2+n+idx[away]]
    a=b[0]-ha+b[2+idx[away]]+b[2+n+idx[home]]
    if m['family']=='poisson':h,a=math.exp(min(h,6)),math.exp(min(a,6))
    return max(h,.05),max(a,.05)

def poisson_win(h,a):
    limit=math.ceil(max(h,a)+12*math.sqrt(max(h,a))+30)
    # Recurrence is stable for the score means admitted by the fitted link.
    ph,pa=math.exp(-h),math.exp(-a);lower_a=0.;p=0.
    for k in range(limit+1):
        p+=ph*(lower_a+.5*pa)
        lower_a+=pa
        ph*=h/(k+1);pa*=a/(k+1)
    return max(0.,min(1.,p))

def assessment(m,validation,home,away,neutral=False,spread=None,total=None,eligible=True):
    s=scores(m,home,away,neutral)
    if not s:return {'status':'PASS','reason':'No prepared model for both teams.'}
    h,a=s;margin=h-a;combined=h+a
    out={'status':'PASS','home_score':h,'away_score':a,'margin':margin,'total':combined,
      'win_probability':None,'spread_status':'PASS','total_status':'PASS','confidence_score':None,
      'reason':'Unvalidated model: descriptive projections only.','limitations':m['limitations']}
    i=m['teams'].index(home);j=m['teams'].index(away);n=len(m['teams']);beta=m['beta']
    factors=[('League scoring baseline',beta[0],beta[0]),('Venue effect',0 if neutral else -beta[1],0 if neutral else beta[1]),('Own attack',beta[2+j],beta[2+i]),('Opponent defensive concession',beta[2+n+i],beta[2+n+j])]
    out['contributions']=[{'Factor':label,'Away':math.exp(av) if m['family']=='poisson' else av,'Home':math.exp(hv) if m['family']=='poisson' else hv} for label,av,hv in factors]
    out['contribution_units']='Multiplicative scoring factors (multiply to reconstruct expected score).' if m['family']=='poisson' else 'Scoring-point components; sum before the 0.05-point minimum floor.'
    enough=min(m['counts'].get(home,0),m['counts'].get(away,0))>=MIN_TEAM_GAMES
    if not validation or not validation.get('gate') or not eligible or not enough:
        if not eligible:out['reason']='Retrospective, stale, cross-division or mismatched-season comparison; prospective confidence suppressed.'
        elif not enough:out['reason']='Too few completed games for one or both teams.'
        return out
    raw=poisson_win(h,a) if m['family']=='poisson' else NormalDist().cdf((h-a)/max(validation.get('margin_sd') or 15.,.5))
    raw=max(.001,min(.999,raw));c=validation['calibrator'];z=c['intercept']+c['slope']*math.log(raw/(1-raw))
    p=1/(1+math.exp(-z))
    out.update({'status':'ESTIMATE','win_probability':p,'confidence_score':round(100*abs(2*p-1),1),
      'confidence_label':'Model separation score (not reliability)',
      'reason':'Calibrated on an earlier chronological validation block; independent test results shown below.',
      'margin_interval':[margin+validation['margin_q10'],margin+validation['margin_q90']],
      'total_interval':[combined+validation['total_q10'],combined+validation['total_q90']]})
    if spread is not None:
        errors=validation['margin_errors'];out['spread_probability']=sum(margin+e+spread>0 for e in errors)/len(errors)
        v=validation.get('market_validation',{}).get('spread',{})
        out['spread_evidence']=('Historical-line release gate '+('passed' if v.get('gate') else 'not passed')+f'; n={v.get("n",0)}. Category support is required separately.') if v.get('n') else 'Exploratory residual estimate; no verified historical spread evaluation.'
    if total is not None:
        errors=validation['total_errors'];out['over_probability']=sum(combined+e>total for e in errors)/len(errors)
        v=validation.get('market_validation',{}).get('total',{})
        out['total_evidence']=('Historical-line release gate '+('passed' if v.get('gate') else 'not passed')+f'; n={v.get("n",0)}. Category support is required separately.') if v.get('n') else 'Exploratory residual estimate; no verified historical total evaluation.'
    for kind,line in [('spread',spread),('total',total)]:
        v=validation.get('market_validation',{}).get(kind,{})
        probability=out.get('spread_probability' if kind=='spread' else 'over_probability')
        bounds=v.get('line_range')
        if line is None or probability is None or not v.get('gate') or not bounds or not bounds[0]<=line<=bounds[1]:continue
        separation=max(probability,1-probability)
        category='strong' if separation>=.65 else 'moderate' if separation>=.55 else None
        if category and v.get('categories',{}).get(category,{}).get('supported'):
            out[kind+'_status']=category.upper()
            out[kind+'_evidence']='Independently tested historical-line probability and confidence category; no sportsbook prices or returns modeled.'
    return out
