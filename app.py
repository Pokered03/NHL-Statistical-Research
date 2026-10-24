"""One independent Streamlit dashboard. Rendering performs zero HTTP requests."""
from datetime import datetime,date,time,timezone,timedelta
from html import escape
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo
import streamlit as st
from research.config import SPORT,TITLE,DEFAULT_SEASONS
from research import store
from research.view import CSS,header,table,confidence_cards

st.set_page_config(page_title=TITLE,page_icon='📊',layout='wide')
st.markdown(CSS,unsafe_allow_html=True)
st.markdown('<div class="eyebrow">INDEPENDENT SPORTS INTELLIGENCE · RESEARCH EDITION</div>',unsafe_allow_html=True)
st.title(TITLE)
NY=ZoneInfo('America/New_York')
now=datetime.now(NY)

if not store.DB_PATH.exists():
    st.info('The data worker has not published this sport’s database yet. No statistics or probabilities are invented.')
    st.code('python -m research.pipeline --seasons '+' '.join(map(str,DEFAULT_SEASONS)))
    st.caption('Run the worker outside the Streamlit web process. See README for deployment and data permissions.')
    st.stop()

def revision():
    p=store.DB_PATH.stat();return (p.st_mtime_ns,p.st_size)
@st.cache_data(ttl=300,max_entries=4)
def meta(rev):return store.metadata()
@st.cache_data(ttl=300,max_entries=12)
def teams(season,rev):return store.teams(season)
@st.cache_data(ttl=180,max_entries=48)
def scheduled(season,day,rev):return store.schedule(season,day)
@st.cache_data(ttl=300,max_entries=32)
def snapshot(season,tid,rev):return store.snapshot(season,tid)
@st.cache_data(ttl=300,max_entries=4)
def model(season,rev):return store.model(season)

try:
    rev=revision();metadata=meta(rev);status=metadata.get('status',{});validation=metadata.get('validation',{})
    if status.get('fixture'):
        st.warning('TEST FIXTURE — synthetic data for software validation only. All confidence assessments are PASS.')
    available=store.seasons()
    if not available:st.warning('No schedules available.');st.stop()
    control=st.columns([1,1,2])
    season=control[0].selectbox('Season (ending year)',available)
    selected_date=control[1].date_input('Research date (Eastern)',now.date())
    mode=control[2].radio('Comparison mode',['Scheduled matchup','Manual teams'],horizontal=True)
    roster=teams(season,rev);names={t['id']:t['name'] for t in roster};info={t['id']:t for t in roster}
    scheduled_game=None;neutral=False
    if mode=='Scheduled matchup':
        games=scheduled(season,selected_date.isoformat(),rev)
        if not games:
            st.info(f'No published {SPORT.upper()} matchups for {selected_date:%b %d, %Y} in the selected season. Use Manual teams or select another date.')
            dates=store.query('SELECT date,COUNT(*) games FROM games WHERE season=? GROUP BY date ORDER BY abs(julianday(date)-julianday(?)) LIMIT 6',(season,selected_date.isoformat()))
            if dates:st.caption('Nearby source dates: '+' · '.join(f'{r["date"]} ({r["games"]} games)' for r in dates))
            st.caption('Latest successful refresh: '+str(status.get('last_successful_update','Not available')))
            with st.expander('Sources and data coverage',expanded=True):
                st.json(status)
            st.stop()
        labels={g['id']:f'{g["away_name"]} at {g["home_name"]} · '+(datetime.fromisoformat(g['start']).astimezone(NY).strftime('%I:%M %p ET').lstrip('0') if g.get('start') else 'Time unavailable')+f' · {g["status"].upper()}' for g in games}
        gid=st.selectbox('Scheduled matchup',list(labels),format_func=labels.get)
        scheduled_game=next(g for g in games if g['id']==gid)
        a,b=scheduled_game['away'],scheduled_game['home'];neutral=bool(scheduled_game['neutral'])
        context=f'{selected_date:%b %d, %Y} · {scheduled_game["venue"] or "Venue unavailable"} · {scheduled_game["status"].upper()}'
    else:
        if len(names)<2:st.info('Two verified teams are required.');st.stop()
        cols=st.columns([2,2,1])
        a=cols[0].selectbox('Team A (away by default)',list(names),format_func=names.get)
        b=cols[1].selectbox('Team B (home by default)',[t for t in names if t!=a],format_func=names.get)
        neutral=cols[2].checkbox('Neutral venue')
        context=f'Manual comparison · {selected_date:%b %d, %Y} · '+('Neutral venue' if neutral else 'Team B at home')
    sa,sb=snapshot(season,a,rev),snapshot(season,b,rev)
    recent=st.segmented_control('Recent window',['Last 3','Last 5','Last 10'],default='Last 3') or 'Last 3'
    st.markdown(header(names[a],names[b],sa,sb,context),unsafe_allow_html=True)
    if not sa or not sb:st.warning('One or both teams have no completed-game summary for this season. Missing values are shown as N/A.')
    if sa and sb:
        st.caption(f'Summary prepared: {datetime.fromisoformat(sa["asof"]).astimezone(NY):%b %d, %Y %I:%M %p ET} · Latest final: {names[a]} {sa["last_date"]}; {names[b]} {sb["last_date"]}')
        if selected_date.isoformat()<=max(sa['last_date'],sb['last_date']):st.info('Retrospective comparison: these are season-to-date summaries, not reconstructed pregame statistics. Prospective confidence is suppressed.')
        if max((now.date()-date.fromisoformat(s['last_date'])).days for s in (sa,sb))> (14 if SPORT in ('nfl','cfb') else 7):st.warning('One or both teams’ completed-game data is old. This may be offseason or a delayed upstream feed; check the source coverage.')
    for section in ['Offense','Defense','Situational']:
        st.markdown(table(section,sa,sb,names[a],names[b],recent,'Season' if neutral else 'Away','Season' if neutral else 'Home'),unsafe_allow_html=True)
    st.caption('Colors: top third green · middle third yellow · bottom third red, ranked in the selected split. Every cell shows its observed sample size. N/A means missing data. Swipe tables sideways on iPhone.')
    if SPORT=='mlb':st.caption('† MLB Season batting/pitching cells use official regular-season totals where available. Recent/home/away windows require individual game boxes. Full-season scoring rows may include postseason results. Scope and provider timestamps are separate; no rolling figures are inferred from season totals.')
    st.subheader('Opponent quality & recent form')
    cols=st.columns(2)
    for col,t,s in [(cols[0],a,sa),(cols[1],b,sb)]:
        with col:
            st.markdown('**'+names[t]+'**')
            if s:
                rest=(selected_date-date.fromisoformat(s['last_date'])).days
                st.caption(('Upcoming calendar-day rest: '+str(rest)+' days (1 = back-to-back).') if rest>=0 else 'Research date precedes the latest stored result; rest comparison is retrospective.')
                st.caption('Average opponent adjusted scoring strength: '+(f'{s["sos"]:+.2f}' if s.get('sos') is not None else 'N/A')+' · higher means tougher observed schedule')
                q=s.get('quality_record',{})
                st.caption('Record vs top/bottom third of observed opponents: '+' · '.join(k+' '+str(v['wins'])+'–'+str(v['losses'])+f' (n={v["games"]})' for k,v in q.items()))
                st.caption('Opponent quality uses current season-to-date ratings; it is descriptive and includes hindsight.')
                html=''.join(f'<span class="pill {"good" if g["scored"]>g["allowed"] else "poor" if g["scored"]<g["allowed"] else "average"}">{escape(names.get(g["opp"],g["opp"]))} {g["scored"]:g}–{g["allowed"]:g}</span>' for g in s['last5'])
                st.markdown(html,unsafe_allow_html=True)
                st.caption(f'Statistical game coverage: {s["coverage"]["box_games"]}/{s["coverage"]["completed_games"]} completed games')
                if s.get('defensive_trend'):
                    with st.expander('Last 10 scoring trend'):
                        if st.checkbox('Load scoring trend',key='trend_'+('A' if t==a else 'B')):
                            st.line_chart({'Scored':s['trend'],'Allowed':s['defensive_trend']},height=150)
    with st.expander('Head-to-head history (available seasons)'):
        h2h=store.head_to_head(a,b)
        if h2h:st.dataframe([{k:g[k] for k in ('date','away_name','away_score','home_name','home_score','venue')} for g in h2h],hide_index=True,width='stretch')
        else:st.caption('No head-to-head history in the independently stored seasons.')
    with st.expander('Availability, starters, weather & advanced-data limitations'):
        st.write('Current injury status and future starting goaltenders are unavailable; no projected or confirmed goalie is inferred. Rest and player availability are not calibrated model adjustments in this version.')
        if SPORT in ('nba','cbb'):
            for tid in (a,b):
                for context in store.team_context(season,tid):
                    st.markdown('**'+names[tid]+' — last observed rotation**')
                    st.caption('Source game: '+context['last_observed_game']+' · Retrieved '+context['asof'])
                    st.write('Reported starters: '+', '.join(context['reported_starters']))
                    changes=context.get('starters_changed_from_previous')
                    if changes is not None:st.caption(f'Reported starting-five changes vs preceding recorded game: {changes}')
                    st.dataframe(context['rotation'],hide_index=True,width='stretch')
                    st.caption(context['note'])
        if SPORT=='mlb' and scheduled_game:
            context=store.game_context(scheduled_game['id'])
            if context:
                st.caption('Official MLB probable-pitcher source retrieved '+context['asof'])
                st.markdown('[Official MLB schedule source]('+context['source']+')')
                if not context.get('probable_pitchers'):st.caption('No probable pitchers are currently published for this game.')
                for side,pitcher in context.get('probable_pitchers',{}).items():
                    st.write(side.title()+': '+pitcher['name']+' · '+pitcher['status'])
                    if pitcher.get('season_stats'):st.dataframe([pitcher['season_stats']],hide_index=True,width='stretch')
                st.caption('Probable assignments can change. These are not confirmed starters; no starting-pitcher effect is applied to model probabilities.')
        st.write('Unavailable metrics remain N/A. Expected goals use the published pre-shot model; the xG ≥0.20 chance count is explicitly defined and is not a proprietary high-danger measure. Team goalie GSAx aggregates observed play, not a confirmed future starter.')
    st.subheader('Research assumptions')
    x,y,z=st.columns([1,1,2])
    spread_enabled=x.checkbox('Supply spread')
    spread=x.number_input('Team B spread (negative = favorite)',value=0.,step=.5,disabled=not spread_enabled)
    total_enabled=y.checkbox('Supply total')
    total=y.number_input('Combined goals line',min_value=0.,value=0.,step=.5,disabled=not total_enabled)
    z.caption('Manual lines only. No sportsbook API calls. Spread and total confidence stay on PASS unless their historical-line validation and confidence-category support both pass.')
    m=model(season,rev)
    eligible=False
    if sa and sb and m:
        asof=datetime.fromisoformat(m['asof']);target=datetime.fromisoformat(scheduled_game['start']) if scheduled_game and scheduled_game.get('start') else datetime.combine(selected_date,time(23,59),tzinfo=NY)
        lag=max((selected_date-date.fromisoformat(s['last_date'])).days for s in (sa,sb))
        eligible=target>asof and 0<=lag<=(21 if SPORT in ('nfl','cfb') else 7) and (SPORT!='cfb' or info[a]['division']==info[b]['division']) and not status.get('fixture')
        if scheduled_game and scheduled_game['status']!='scheduled':eligible=False
    from research.predict import assessment
    result=assessment(m,validation,b,a,neutral,spread if spread_enabled else None,total if total_enabled else None,eligible)
    st.markdown(confidence_cards(result,names[a],names[b]),unsafe_allow_html=True)
    st.caption(result.get('reason','Insufficient data.'))
    if result.get('win_probability') is not None:
        st.caption('Win estimates include reported overtime/shootout results. Model reliability is reported by held-out Brier score and calibration error, not by the separation score.')
    if result.get('margin_interval'):st.caption(f'80% empirical scoring interval: Team B margin {result["margin_interval"][0]:+.1f} to {result["margin_interval"][1]:+.1f}; total {result["total_interval"][0]:.1f} to {result["total_interval"][1]:.1f}. Exchangeability is assumed; not a guarantee.')
    with st.expander('How the assessment is derived'):
        st.write('A regularized attack/defense Poisson model adjusts goals for the actual opponents faced and home ice. This is a baseline scoring model; it does not use advanced player or tracking inputs.')
        st.write('Win probabilities use strictly chronological out-of-sample calibration. Separation score = 100 × |2p − 1|. It is not model reliability. Market categories remain PASS without independent historical spread/total testing.')
        if result.get('spread_probability') is not None:st.write(f'Exploratory probability Team B covers supplied spread: {result["spread_probability"]:.1%}. Research estimate; see category support in historical validation.')
        if result.get('over_probability') is not None:st.write(f'Exploratory probability above supplied total: {result["over_probability"]:.1%}. Research estimate; see category support in historical validation.')
        if result.get('contributions'):
            st.caption(result['contribution_units'])
            st.dataframe(result['contributions'],hide_index=True,width='stretch')
            st.caption('Away is Team A; Home is Team B. These coefficients describe scoring history and opponent adjustment, not unmodeled injuries or advanced tracking statistics.')
        if m:
            h,a_score=result.get('home_score'),result.get('away_score')
            if h is not None:st.write(f'Adjusted expected scoring: {names[b]} {h:.1f}; {names[a]} {a_score:.1f}. Expected margin follows from these two estimates. See Methodology for the attack/defense equation and limitations.')
    with st.expander('Historical validation & calibration',expanded=True):
        if validation.get('status')=='tested':
            vc=st.columns(4)
            for col,label,key in [(vc[0],'Held-out games','n'),(vc[1],'Brier score','brier'),(vc[2],'Margin MAE','margin_mae'),(vc[3],'Total MAE','total_mae')]:col.metric(label,str(validation.get(key)) if key=='n' else f'{validation.get(key,0):.3f}')
            st.caption(f'Independent test: {validation["test_from"]} through {validation["test_through"]} · Calibration error {validation["ece"]:.3f} · Probability gate '+('passed' if validation.get('gate') else 'not passed'))
            st.dataframe(validation.get('calibration_bins',[]),hide_index=True,width='stretch')
        else:st.info('No sufficient real-data chronological validation yet. Confidence remains PASS.')
        st.json({k:v for k,v in validation.items() if k not in ('margin_errors','total_errors')})
    with st.expander('Sources, timestamps & coverage'):
        source=status.get('source',{})
        if source.get('url'):st.markdown(f'[{source.get("name","Data source")}]({source["url"]})')
        st.write(source.get('license','Source license not supplied.'))
        st.write('Last successful data-worker update: '+str(status.get('last_successful_update','Unavailable')))
        st.dataframe(status.get('coverage',[]),hide_index=True,width='stretch')
        for warning in status.get('warnings',[]):st.caption(warning)
        if metadata.get('quality_audit'):st.json(metadata['quality_audit'])
        if metadata.get('reference_sources'):st.json(metadata['reference_sources'])
        st.caption('No paid data sources or Odds API keys are used. Team names are text; logos are omitted pending verified usage rights.')
    with st.expander('Performance and data health'):
        import resource
        peak_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
        st.write(f'Peak web-process memory since startup: {peak_mib:.1f} MiB')
        for label,paths in [('Hosting memory limit',['/sys/fs/cgroup/memory.max','/sys/fs/cgroup/memory/memory.limit_in_bytes']),('Current hosting memory usage',['/sys/fs/cgroup/memory.current','/sys/fs/cgroup/memory/memory.usage_in_bytes'])]:
            observed=None
            for location in paths:
                try:
                    raw=Path(location).read_text().strip()
                    if raw.isdigit() and int(raw)<2**60:
                        observed=int(raw)/1024**2
                        break
                except OSError:
                    pass
            st.write(f'{label}: {observed:.1f} MiB' if observed is not None else f'{label}: not exposed by this host')
        st.caption('Host usage includes other container processes and file cache; process memory measures this app. Local resource targets do not certify long-term hosted stability.')
    st.caption('Independent statistical research · Model and source limitations apply · No picks, parlays or automated wagers')
    st.session_state['_research_render_count']=st.session_state.get('_research_render_count',0)+1
    if st.session_state['_research_render_count']%16==0:
        import gc
        gc.collect()  # reclaim cyclic UI objects during sustained matchup research
except (sqlite3.Error,ValueError,KeyError,OSError) as exc:
    st.error('This sport’s published data could not be read. Its last valid data file may need republishing. Other dashboards are independent.')
    st.caption(f'Diagnostic: {type(exc).__name__}')
    st.stop()
