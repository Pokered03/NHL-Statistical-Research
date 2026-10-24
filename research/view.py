"""Responsive, escaped matchup tables modeled on the supplied reference."""
from html import escape
from .metrics import METRICS,color,advantage
CSS='''<style>
:root{color-scheme:dark}.stApp{background:#080b10;color:#f4f6fb}.block-container{max-width:1600px;padding:1.2rem 1rem 3rem}h1{font-size:1.75rem!important}h2,h3{color:#31d6f0!important}.eyebrow{color:#31d6f0;font:700 11px/1.5 sans-serif;letter-spacing:.16em;text-transform:uppercase}.match-header{display:grid;grid-template-columns:1fr auto 1fr;gap:16px;background:linear-gradient(120deg,#161c26,#0d1119);padding:22px 18px;border:1px solid #313947;border-radius:9px}.match-header .right{text-align:right}.team-name{font-size:clamp(19px,3vw,32px);font-weight:800;line-height:1.1}.team-info{color:#b4c0ce;font-size:12px;margin-top:8px}.divider{color:#4d5a6d;align-self:center;font-size:12px}.strip{background:#086579;padding:10px 16px;display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap;font-size:12px;margin:9px 0 16px}.section-title{display:flex;justify-content:space-between;color:#31d6f0;font-size:13px;font-weight:800;text-transform:uppercase;padding:10px 8px;background:#111923;border-top:1px solid #293342}.table-scroll{overflow-x:auto;border:1px solid #293342;margin-bottom:12px}.research{width:100%;border-collapse:collapse;min-width:850px;font-variant-numeric:tabular-nums;font-size:12px}.research th{color:#bec8d5;background:#222935;padding:7px 6px;white-space:nowrap;font-size:10px;text-transform:uppercase}.research td{padding:7px 6px;border-bottom:1px solid #242b36;text-align:center;font-weight:650}.research tr:nth-child(even){background:#141a24}.research tr:nth-child(odd){background:#0c1118}.research .metric{text-align:left;min-width:145px;max-width:210px;font-size:12px}.research .direction{font-size:9px;color:#98a5b8;display:block;font-weight:400}.good{color:#5ff887}.average{color:#ffe566}.poor{color:#ff707f}.missing{color:#748197}.adv{border-left:1px solid #303b4b;border-right:1px solid #303b4b;color:#31d6f0;max-width:90px}.sample{font-size:9px;color:#7e8c9f;font-weight:400}.pill{display:inline-block;border:1px solid #354153;padding:4px 7px;margin:3px;font-size:11px;border-radius:4px}.confidence-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:10px 0}.confidence{background:#131923;border:1px solid #344052;border-radius:6px;padding:16px}.confidence-label{font-size:11px;font-weight:750;color:#c0cad8;letter-spacing:.05em}.confidence-number{font-size:24px;font-weight:800;margin:8px 0;color:#ffe566}.confidence-text{font-size:12px;color:#adb9ca;line-height:1.6}.note{font-size:11px;color:#9cabbf;line-height:1.6}a{color:#31d6f0}@media(max-width:600px){.block-container{padding:.8rem .6rem 2rem}.match-header{padding:15px 12px;gap:8px}.confidence-grid{grid-template-columns:1fr}.research{font-size:11px}.strip{font-size:11px}}
</style>'''

def fmt(v,key):
    if v is None:return 'N/A'
    if key in ('avg','obp','slg','whip'):return f'{v:.3f}'
    if key=='win':return f'{v:.0%}'
    return f'{v:.2f}' if abs(v)<10 else f'{v:.1f}'

def cell(obj,key):
    if not obj or obj.get('value') is None:return '<td class="missing">N/A</td>'
    cls=color(obj.get('rank'),obj.get('pop'))
    return f'<td class="{cls}" title="{escape(obj.get("source_note","Observed game-box aggregate"),quote=True)}">{fmt(obj["value"],key)}{"†" if obj.get("source_note") else ""}<span class="sample"> · n={obj["n"]}</span></td>'

def table(section,a,b,left,right,recent='Last 3',leftsplit='Away',rightsplit='Home'):
    a=a or {'stats':{}};b=b or {'stats':{}}
    s=f'<div class="section-title"><span>{escape(left)} · {section}</span><span>{escape(right)} · {section}</span></div><div class="table-scroll"><table class="research"><thead><tr><th>Statistic</th><th>Season</th><th>{leftsplit}</th><th>1st half</th><th>{recent}</th><th>Rank</th><th>Advantage</th><th>Rank</th><th>{recent}</th><th>1st half</th><th>{rightsplit}</th><th>Season</th></tr></thead><tbody>'
    def get(obj,split,key):return obj.get('stats',{}).get(split,{}).get(key,{})
    for m in [m for m in METRICS if m.section==section]:
        x=get(a,recent,m.key);y=get(b,recent,m.key);avx=x.get('value');avy=y.get('value');basis=''
        if m.key in ('adjusted_ortg','adjusted_drtg'):
            avx=get(a,'Season',m.key).get('value');avy=get(b,'Season',m.key).get('value');basis=' (season)'
        adv=advantage(avx,avy,m.direction)
        direction='↑ higher favorable' if m.direction>0 else '↓ lower favorable' if m.direction<0 else '↔ descriptive'
        s+=f'<tr><td class="metric" title="{escape(m.note,quote=True)}">{escape(m.label)}<span class="direction">{direction}</span></td>'
        for split in ('Season',leftsplit,'1st half',recent):s+=cell(get(a,split,m.key),m.key)
        for obj,center in [(x,False),(None,True),(y,False)]:
            if center:s+=f'<td class="adv">{escape((left if adv=="A" else right if adv=="B" else adv)+basis)}</td>'
            else:
                rank=obj.get('rank');pop=obj.get('pop');s+=f'<td class="{color(rank,pop)}">{f"{rank}/{pop}" if rank else "—"}</td>'
        for split in (recent,'1st half',rightsplit,'Season'):s+=cell(get(b,split,m.key),m.key)
        s+='</tr>'
    return s+'</tbody></table></div>'

def header(a,b,sa,sb,context):
    def info(s):
        if not s:return 'No completed-game summary'
        return f'{s["record"]} vs covered opponents · Adjusted scoring rank {s.get("strength_rank") or "N/A"} · {s["games"]} games'
    return f'<div class="match-header"><div><div class="eyebrow">TEAM A</div><div class="team-name">{escape(a)}</div><div class="team-info">{escape(info(sa))}</div></div><div class="divider">VS</div><div class="right"><div class="eyebrow">TEAM B</div><div class="team-name">{escape(b)}</div><div class="team-info">{escape(info(sb))}</div></div></div><div class="strip"><span>{escape(context)}</span><span>STATISTICAL MATCHUP RESEARCH</span><span>↑ Higher favorable · ↓ Lower favorable</span></div>'

def confidence_cards(result,a,b):
    p=result.get('win_probability');score=result.get('confidence_score');margin=result.get('margin');total=result.get('total')
    cards=[('MONEYLINE CONFIDENCE',f'{1-p:.1%} / {p:.1%}' if p is not None else 'PASS',f'{a} / {b}. '+(f'Separation score {score:.1f}/100. This measures model separation, not certainty.' if score is not None else 'Calibrated probability withheld.')),
      ('SPREAD CONFIDENCE',result.get('spread_status','PASS'),f'Projected {b} margin: {margin:+.1f}. '+result.get('spread_evidence','Confidence category unsupported or no supplied line.') if margin is not None else 'Insufficient verified scoring history.'),
      ('TOTAL CONFIDENCE',result.get('total_status','PASS'),f'Projected combined score: {total:.1f}. '+result.get('total_evidence','Confidence category unsupported or no supplied line.') if total is not None else 'Insufficient verified scoring history.')]
    return '<div class="section-title">STATISTICAL CONFIDENCE LEVELS</div><div class="confidence-grid">'+''.join(f'<div class="confidence"><div class="confidence-label">{label}</div><div class="confidence-number">{escape(value)}</div><div class="confidence-text">{escape(txt)}</div></div>' for label,value,txt in cards)+'</div>'
