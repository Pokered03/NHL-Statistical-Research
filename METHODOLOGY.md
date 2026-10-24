# Methodology and validation

## Aggregation and direction

Every metric declares higher favorable, lower favorable or descriptive. Ratios are computed by summing observed numerators and denominators, not by averaging game percentages. Missing fields stay missing. A rate with zero denominator is unavailable. Every rendered cell exposes the number of observed games; differing source completeness can make samples unequal.

Recent splits use the last 3/5/10 completed games; home/away excludes neutral venues. Rankings are competition ranks within the observed split population, with ties sharing a rank. The best third is green, middle third yellow and worst third red. Descriptive metrics are not labeled as advantages. FBS and FCS use separate ranking pools. Strength-of-schedule descriptions use current season-to-date opponent ratings, so historical descriptive summaries contain hindsight and must not be treated as backtest inputs.

## Offensive and defensive efficiency

Basketball possessions = mean of both teams’ `(FGA − ORB + turnovers + 0.44 × FTA)`. This is an estimate and includes overtime; it is not regulation-minute adjusted pace. Offensive rating is points per 100 estimated possessions, defensive rating is points allowed per 100, and net rating is their difference. eFG = `(FGM + 0.5 × 3PM)/FGA`; TS = `PTS/(2 × (FGA + 0.44 × FTA))`. Season-only adjusted efficiencies fit the same regularized attack/defense model to per-100-possession scoring. This model is not a branded third-party rating.

MLB OPS = OBP + SLG. WHIP = `(H + BB)/IP`, with exact defensive outs / 3 for IP. ERA = `9 × earned runs / IP`. Team FIP uses `(13×HR + 3×(BB+HBP) − 2×K)/IP` plus a computed season league constant that reconciles league FIP with league ERA. FIP has no park adjustment; xFIP/wRC+/Statcast values are not approximated. Team passer ratings combine all passers, using the NFL formula for NFL and NCAA efficiency formula for college when the required primitives exist.

Basketball box scores are quarantined when field-goal/free-throw totals disagree with the final score or shot-count constraints fail. Both teams’ box metrics are excluded for that game to protect possession estimates. The final result is retained for scoring research. The quality-audit metadata records affected games. Quarantine reduces metric sample sizes rather than replacing missing values.

## Opponent-adjusted scoring model

For continuous scoring sports (NFL, NBA, college football and college basketball):

`expected score = intercept + venue coefficient + team attack + opponent defensive concession`.

For MLB/NHL, a penalized Poisson model uses the logarithm of that expected score. Team attack and defensive concession parameters have ridge penalty 8; the home coefficient penalty is 1 and the intercept is unpenalized. Coefficients are fitted by sparse least squares, or penalized Poisson IRLS. These penalties are fixed engineering choices, not claimed optimal parameters. Home and away use opposite venue indicators; neutral uses zero.

Projected margin is home expected score minus away expected score; projected total is their sum. No injury, individual quarterback, pitcher, goalie, weather, fatigue or lineup-role coefficient is currently used. Advanced statistics shown in tables are descriptive and are not automatically model inputs. Scoring includes reported overtime and shootout scores. A Poisson model can understate baseball/hockey scoring dependence and overdispersion; empirical validation must be reviewed.

## Chronological validation

Each season is fitted separately, resetting team ratings at the new season. Models are refitted at most once per seven-day block using only games on dates strictly before that block. Evaluation excludes teams with insufficient earlier games and excludes ties from win calibration. No same-date final results are used as training inputs. The prediction audit includes the training-last-date for each historical game.

The earliest roughly 55% of chronological out-of-sample predictions form the probability calibration set. The calendar boundary keeps a whole day in a single partition. A logistic intercept/slope calibrator is fitted on those predictions, with a small regularization term. The later partition is a held-out test and is never used to fit the calibrator. This is one fixed chronological partition, not repeated cross-validation, and results can be sensitive to the split and changing teams.

Reported measures: held-out Brier score, accuracy, calibration bins and expected calibration error, margin MAE, total MAE, baseline scoring-model errors, early/late sample counts, and 80% empirical margin-interval coverage. The probability baseline shown is 50%; the scoring baseline retains venue but omits team adjustments. Neither baseline represents a sportsbook.

## Release gate and statistical confidence

Probability display requires at least 200 calibration and 200 held-out games, successful calibration, ECE no greater than 0.10 and Brier better than the 50% baseline. The current matchup must have enough current-season games, recent source results and prospective timing; retrospective and cross FBS/FCS comparisons are suppressed. Passing these development safeguards is not proof of model correctness, stable future performance, profitability or completeness.

`separation score = 100 × abs(2 × calibrated win probability − 1)`.

The separation score measures how far the estimate is from 50%, not confidence in the model. Held-out Brier/calibration results measure empirical model reliability separately. Win probabilities are conditional on a decisive result because draws were omitted from calibration. This is particularly relevant to NFL.

Scoring intervals add calibration-block residual quantiles to current projections; they are empirical prediction intervals, not posterior credible intervals. Exchangeability and stable residual distributions are assumptions. Optional manual spread/total residual estimates are exploratory. Spread/total assessment categories remain PASS because historical category reliability against real market lines has not been independently validated. No price-based edge, expected betting value or recommendation is produced.

## Known limits

Historical source revisions are reflected in downloaded final scores; unavailable as-published vintages can introduce revision bias. Source coverage, excluded opponents and missing boxes alter samples. Historical descriptive pages are not point-in-time reconstructions. NFL historical closing-line tests are implemented, but the observed baseline fails both market release gates. Other sports still lack integrated market-line backtests. Independent browser/mobile QA and hosted-limit testing remain incomplete. Do not describe this development build as a finished professional service.

## Expanded source-specific research

NHL event metrics are calculated from bounded Parquet batches. Corsi includes blocked attempts attributed to the shooter (the event owner is the blocker in this source). Fenwick excludes blocked attempts. Both include all strengths and exclude shootouts. Each event is deduplicated by game/event ID. A completed history must match both teams’ box shots on target before advanced outputs are accepted. Publisher xG is a model estimate, not a measured goal. Full-game xG is withheld when any eligible unblocked shot lacks an xG value; the observed-xG-per-modeled-attempt rate remains separately labeled. The xG ≥0.20 counter is an explicit research definition rather than a proprietary high-danger label. Team pre-shot goalie GSAx aggregates all goalies and excludes identified empty-net/shootout attempts; it is not a confirmed-starter forecast.

College football play-by-play requires an observed final ending whose score matches the schedule final. EPA/success count observed scrimmage plays; explosive rates have their own observed-play denominator. Red-zone zero opportunities are asserted only when drive identities were observed. Halftime values require an observed second-period ending. The publisher’s line-yards metric is a rushing-line proxy; recorded hurries/sacks are not a full tracking pressure rate. No proprietary line grade is invented.

Basketball bench/role context requires five reported starters and exact player-point reconciliation. Recorded minutes are not evidence of current medical availability. Last-observed rotation/context remains separate from model probabilities; conflicting active/DNP fields are ignored. Offensive-ending share describes observed FGA + 0.44×FTA + turnovers; it is not official usage rate.

MLB Season reference cells marked † are official regular-season aggregate summaries and expose their own sample/scope/source timestamp. They are not used to synthesize missing rolling/home/away game logs. Probable pitchers come from a timestamped official schedule; they remain explicitly probable and can change. Individual pitching stats use a single/aggregate season split, withholding ambiguous multi-team splits rather than silently combining them. These context fields are not predictive adjustments.

## Historical market-line category validation

NFL historical closing lines are free nflverse schedule fields. Their sign is normalized to negative home-favorite spread. These lines are used for evaluation, not as model training inputs. Calibration-block scoring residuals produce exploratory cover/over probabilities at held-out closing lines; pushes are excluded and counted. A market probability gate requires ≥200 held-out non-push comparisons, ECE ≤0.10 and Brier below 0.25. Moderate (55–65%) and strong (≥65%) separation categories additionally need ≥50 held-out observations and a 95% Wilson lower bound above 50% for the selected direction. Manual lines outside the historical support range cannot release a category. These gates are fixed safeguards, not profitability tests. No sportsbook prices, returns or automatic recommendations are evaluated. The observed NFL baseline fails both market gates and therefore remains PASS. Do not tune on that held-out result to force a passing score; model changes need a new untouched evaluation period.
