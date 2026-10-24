"""Opponent-adjusted scoring models and chronological calibration. Worker only fits."""
import math
from collections import Counter
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import lsqr
from scipy.optimize import minimize
from scipy.special import expit,logit
from scipy.stats import skellam
from .config import SPORT, MIN_TEAM_GAMES

VERSION='adjusted-score-v1'

def fit(games):
    ids=sorted({t for g in games for t in (g['home'],g['away'])}); index={t:i for i,t in enumerate(ids)}
    if not games:return None
    n=len(ids); rr=[];cc=[];vv=[];y=[]
    for g in games:
        for team,opp,home,score in [(g['home'],g['away'],1,g['home_score']),(g['away'],g['home'],-1,g['away_score'])]:
            r=len(y);rr.extend([r]*4);cc.extend([0,1,2+index[team],2+n+index[opp]])
            vv.extend([1,0 if g['neutral'] else home,1,1]); y.append(score)
    X=sparse.csr_matrix((vv,(rr,cc)),shape=(len(y),2+2*n)); y=np.array(y,float)
    penalty=np.r_[0.,1.,np.repeat(8.,2*n)]
    if SPORT in ('mlb','nhl'):
        # Penalized Poisson IRLS. The link preserves non-negative scoring means.
        beta=np.zeros(X.shape[1]);beta[0]=math.log(max(y.mean(),.1))
        for _ in range(40):
            eta=np.clip(X@beta,-5,6);mu=np.exp(eta);w=np.sqrt(mu)
            z=eta+(y-mu)/mu
            A=sparse.vstack([X.multiply(w[:,None]),sparse.diags(np.sqrt(penalty))]).tocsr()
            b=np.r_[w*z,np.zeros(X.shape[1])]
            new=lsqr(A,b,atol=1e-7,btol=1e-7,iter_lim=500)[0]
            if np.max(np.abs(new-beta))<1e-5: beta=new;break
            beta=new
        family='poisson'
    else:
        A=sparse.vstack([X,sparse.diags(np.sqrt(penalty))]).tocsr()
        beta=lsqr(A,np.r_[y,np.zeros(X.shape[1])],atol=1e-8,btol=1e-8,iter_lim=500)[0];family='gaussian'
    counts=Counter(t for g in games for t in (g['home'],g['away']))
    return {'version':VERSION,'family':family,'teams':ids,'beta':beta.tolist(),'counts':dict(counts),
      'training_games':len(games),'training_last_date':max(g['date'] for g in games),'league_mean':float(y.mean()),
      'limitations':['No player availability, starter/goalie or weather adjustments.','Team scoring model; advanced metrics are descriptive and are not model inputs.']}

def scores(m,home,away,neutral=False,adjusted=True):
    if not m or home==away:return None
    idx={t:i for i,t in enumerate(m['teams'])}
    if home not in idx or away not in idx:return None
    b=m['beta'];n=len(idx);ha=0 if neutral else b[1]
    h=b[0]+ha+(b[2+idx[home]]+b[2+n+idx[away]] if adjusted else 0)
    a=b[0]-ha+(b[2+idx[away]]+b[2+n+idx[home]] if adjusted else 0)
    if m['family']=='poisson':h,a=math.exp(min(h,6)),math.exp(min(a,6))
    return max(h,.05),max(a,.05)

def raw_probability(m,h,a,sd=None):
    if m['family']=='poisson':
        # Ties at end of regulation/Poisson score process allocate half to each team.
        return float(1-skellam.cdf(0,h,a)+.5*skellam.pmf(0,h,a))
    from scipy.special import ndtr
    return float(ndtr((h-a)/max(sd or 15.,.5)))

def adjusted_strength(m,team):
    if not m or team not in m['teams']:return None
    i=m['teams'].index(team);n=len(m['teams']);b=m['beta']
    if m['family']=='poisson':return math.exp(b[0]+b[2+i])-math.exp(b[0]+b[2+n+i])
    return b[2+i]-b[2+n+i]

def validation_metrics(rows,probs):
    y=np.array([r['winner'] for r in rows]);p=np.array(probs)
    bins=[];ece=0.
    for lo in np.arange(0,1,.1):
        mask=(p>=lo)&(p<lo+.100000001)
        # Non-overlapping bins via integer bucket.
        mask=np.minimum((p*10).astype(int),9)==round(lo*10)
        if mask.any():
            observed=float(y[mask].mean());pred=float(p[mask].mean());n=int(mask.sum())
            bins.append({'lower':round(float(lo),1),'n':n,'predicted':pred,'observed':observed})
            ece+=n/len(y)*abs(observed-pred)
    errors=np.array([r['actual_margin']-r['margin'] for r in rows]);tot=np.array([r['actual_total']-r['total'] for r in rows])
    return {'n':len(rows),'brier':float(np.mean((p-y)**2)),'baseline_brier':float(np.mean((.5-y)**2)),
      'accuracy':float(np.mean((p>=.5)==(y>=.5))),'margin_mae':float(np.mean(abs(errors))),
      'total_mae':float(np.mean(abs(tot))),'ece':ece,'calibration_bins':bins,
      'margin_interval_80_coverage':None}

def backtest(games):
    """Refit every seven days on prior dates within that season; never same-day results."""
    oos=[]
    for season in sorted({g['season'] for g in games}):
        sg=sorted([g for g in games if g['season']==season],key=lambda g:(g['date'],g['id']))
        days=sorted({g['date'] for g in sg});last_fit=None;m=None;residual_sd=None
        for day in days:
            if last_fit is None or (np.datetime64(day)-np.datetime64(last_fit)).astype(int)>=7:
                train=[g for g in sg if g['date']<day]
                if len(train)<40:continue
                m=fit(train);last_fit=day
                err=[(g['home_score']-g['away_score'])- (lambda s:s[0]-s[1])(scores(m,g['home'],g['away'],g['neutral'])) for g in train]
                residual_sd=float(np.std(err,ddof=1)) if len(err)>1 else None
            if not m:continue
            for g in [g for g in sg if g['date']==day]:
                if min(m['counts'].get(g['home'],0),m['counts'].get(g['away'],0))<MIN_TEAM_GAMES:continue
                s=scores(m,g['home'],g['away'],g['neutral']);base=scores(m,g['home'],g['away'],g['neutral'],False)
                h,a=s;p=raw_probability(m,h,a,residual_sd)
                if g['home_score']==g['away_score']:continue  # win assessment excludes draws; disclosed
                oos.append({'date':day,'season':season,'game_id':g['id'],'training_last_date':m['training_last_date'],
                  'p':p,'winner':float(g['home_score']>g['away_score']),'margin':h-a,'total':h+a,
                  'actual_margin':g['home_score']-g['away_score'],'actual_total':g['home_score']+g['away_score'],
                  'home_spread':g.get('home_spread'),'market_total':g.get('market_total'),'baseline_margin':base[0]-base[1],'baseline_total':sum(base),'team_games':min(m['counts'][g['home']],m['counts'][g['away']])})
    oos.sort(key=lambda r:(r['date'],r['game_id']))
    if len(oos)<100:return {'version':VERSION,'status':'insufficient','oos_games':len(oos),'gate':False,'reason':'At least 100 chronological predictions required to fit a calibration split.'},oos
    # Split by calendar dates, so a single day cannot straddle calibration and held-out test.
    boundary=oos[int(len(oos)*.55)]['date'];cal=[r for r in oos if r['date']<=boundary];test=[r for r in oos if r['date']>boundary]
    if not test:return {'status':'insufficient','gate':False,'reason':'No independent test dates.'},oos
    x=np.array([logit(np.clip(r['p'],.001,.999)) for r in cal]);y=np.array([r['winner'] for r in cal])
    def loss(v):
        p=np.clip(expit(v[0]+v[1]*x),1e-8,1-1e-8)
        return -np.mean(y*np.log(p)+(1-y)*np.log(1-p))+.002*((v[1]-1)**2+v[0]**2)
    opt=minimize(loss,[0.,1.],bounds=[(-2,2),(0,3)])
    intercept,slope=[float(z) for z in opt.x]
    p=[float(expit(intercept+slope*logit(np.clip(r['p'],.001,.999)))) for r in test]
    report=validation_metrics(test,p)
    me=np.array([r['actual_margin']-r['margin'] for r in cal]);te=np.array([r['actual_total']-r['total'] for r in cal])
    report.update({'version':VERSION,'status':'tested','gate':bool(len(test)>=200 and len(cal)>=200 and report['ece']<=.10 and report['brier']<report['baseline_brier'] and opt.success),
      'calibration_n':len(cal),'calibration_through':boundary,'test_from':test[0]['date'],'test_through':test[-1]['date'],
      'oos_games':len(oos),'calibrator':{'intercept':intercept,'slope':slope},
      'margin_errors':me.tolist(),'total_errors':te.tolist(),
      'margin_sd':float(np.std(me,ddof=1)),'margin_q10':float(np.quantile(me,.1)),'margin_q90':float(np.quantile(me,.9)),
      'total_q10':float(np.quantile(te,.1)),'total_q90':float(np.quantile(te,.9)),
      'baseline_margin_mae':float(np.mean([abs(r['actual_margin']-r['baseline_margin']) for r in test])),
      'baseline_total_mae':float(np.mean([abs(r['actual_total']-r['baseline_total']) for r in test])),
      'reason':'Gate requires >=200 calibration and test games, ECE <=0.10, Brier better than 50%, successful calibration. Thresholds are engineering safeguards, not proof of profitability.',
      'exclusions':'Draws excluded from win calibration; all scoring includes overtime/shootout scores as reported. No historical market prices are available; spread/total category reliability is unvalidated.'})
    report['margin_interval_80_coverage']=float(np.mean([report['margin_q10']<=r['actual_margin']-r['margin']<=report['margin_q90'] for r in test]))
    from .market_validation import evaluate
    report['market_validation']=evaluate(cal,test)
    for name,subset in [('early',[r for r in test if r['team_games']<10]),('late',[r for r in test if r['team_games']>=10])]:
        report[name]={'n':len(subset),'margin_mae':float(np.mean([abs(r['actual_margin']-r['margin']) for r in subset])) if subset else None}
    return report,oos

def assessment(m,validation,home,away,neutral=False,spread=None,total=None,eligible=True):
    s=scores(m,home,away,neutral)
    if not s:return {'status':'PASS','reason':'No prepared model for both teams.'}
    h,a=s;margin=h-a;combined=h+a
    out={'status':'PASS','home_score':h,'away_score':a,'margin':margin,'total':combined,
      'win_probability':None,'spread_status':'PASS','total_status':'PASS','confidence_score':None,
      'reason':'Unvalidated model: descriptive projections only.','limitations':m['limitations']}
    enough=min(m['counts'].get(home,0),m['counts'].get(away,0))>=MIN_TEAM_GAMES
    if not validation or not validation.get('gate') or not eligible or not enough:
        if not eligible:out['reason']='Retrospective, stale, cross-division or mismatched-season comparison; prospective confidence suppressed.'
        elif not enough:out['reason']='Too few completed games for one or both teams.'
        return out
    raw=raw_probability(m,h,a,validation.get('margin_sd'));c=validation['calibrator']
    p=float(expit(c['intercept']+c['slope']*logit(np.clip(raw,.001,.999))))
    out.update({'status':'ESTIMATE','win_probability':p,'confidence_score':round(100*abs(2*p-1),1),
      'confidence_label':'Model separation score (not reliability)',
      'reason':'Calibrated on an earlier chronological validation block; independent test results shown below.',
      'margin_interval':[margin+validation['margin_q10'],margin+validation['margin_q90']],
      'total_interval':[combined+validation['total_q10'],combined+validation['total_q90']]})
    # Do not turn an unvalidated market assessment into a recommendation.
    if spread is not None:
        out['spread_probability']=float(np.mean(margin+np.array(validation['margin_errors'])+spread>0))
        out['spread_evidence']='Exploratory residual estimate; historical spread validation unavailable.'
    if total is not None:
        out['over_probability']=float(np.mean(combined+np.array(validation['total_errors'])>total))
        out['total_evidence']='Exploratory residual estimate; historical total validation unavailable.'
    return out
