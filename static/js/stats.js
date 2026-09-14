/* ===================================================================
   stats.js — tiny localStorage counters so the Dashboard can show
   real usage ("you've run 4,000 shots") instead of static filler.
=================================================================== */

const QS_STATS_KEY = 'qs_usage_stats';

function qsStatsGet() {
  try {
    return Object.assign({ shotsRun: 0, gatesApplied: 0, statesMeasured: 0 }, JSON.parse(localStorage.getItem(QS_STATS_KEY) || '{}'));
  } catch (e) { return { shotsRun: 0, gatesApplied: 0, statesMeasured: 0 }; }
}

function qsStatsIncrement(field, amount) {
  const s = qsStatsGet();
  s[field] = (s[field] || 0) + amount;
  localStorage.setItem(QS_STATS_KEY, JSON.stringify(s));
  return s;
}
