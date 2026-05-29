"use strict";

// ── Category max points ───────────────────────────────────────────────────────

const METRIC_MAX_POINTS = {
  opps:        15,
  ppvga:       35,
  fiber:       15,
  aia:         10,
  accessories: 10,
  protection:   5,
  rate_plan:    5,
  next_up:      5,
};

// ── Scoring tables ────────────────────────────────────────────────────────────

// Sales-to-goal: 125 %+ = full points; every 10-pp tier below = −10 %.
const SALES_MULTIPLIERS = {
  125: 1.0, 100: 0.9, 90: 0.8, 80: 0.7,
   70: 0.6,  60: 0.5, 50: 0.4, 40: 0.3,
   30: 0.2,  20: 0.1,  0: 0.0,
};
const SALES_THRESHOLDS = Object.keys(SALES_MULTIPLIERS)
  .map(Number)
  .sort((a, b) => b - a);

// Attach-rate exact breakpoint tables: [[minPct, points], ...]
const PROTECTION_TABLE = [[70, 5.0],[68, 4.5],[66, 4.0],[63, 3.5],[60, 3.0]];
const RATE_PLAN_TABLE  = [[82, 5.0],[80, 4.5],[78, 4.0],[76, 3.5],[74, 3.0]];
const NEXT_UP_TABLE    = [[80, 5.0],[78, 4.5],[76, 4.0],[74, 3.5],[72, 3.0]];

const ATTACH_TABLES = {
  protection: PROTECTION_TABLE,
  rate_plan:  RATE_PLAN_TABLE,
  next_up:    NEXT_UP_TABLE,
};

// ── Commission rates by rank tier ─────────────────────────────────────────────

const COMMISSION_TIERS = {
  rank_8: {
    new_voice_premium:  35,
    new_voice_extra:    25,
    new_voice_starter:  15,
    fiber_aia:          50,
    voice_upgrade:       5,
    accessories_pct:    0.06,
    pa1:                 3,
    pa4:                 6,
    htp:                 6,
  },
  rank_9: {
    new_voice_premium:  70,
    new_voice_extra:    50,
    new_voice_starter:  25,
    fiber_aia:          60,
    voice_upgrade:       5,
    accessories_pct:    0.07,
    pa1:                 4,
    pa4:                10,
    htp:                10,
  },
};

// ── Core scoring ──────────────────────────────────────────────────────────────

function percentToPoints(metric, percent) {
  if (percent === null || percent === undefined) return 0;

  const table = ATTACH_TABLES[metric];
  if (table) {
    for (const [threshold, pts] of table) {
      if (percent >= threshold) return pts;
    }
    return 0;
  }

  const maxPts = METRIC_MAX_POINTS[metric];
  if (maxPts === undefined) throw new Error(`Unknown metric: ${metric}`);

  for (const threshold of SALES_THRESHOLDS) {
    if (percent >= threshold) {
      return Math.round(maxPts * SALES_MULTIPLIERS[threshold] * 100) / 100;
    }
  }
  return 0;
}

function computePoints(metrics) {
  const out = {};
  for (const m of Object.keys(METRIC_MAX_POINTS)) {
    if (m in metrics) out[m] = percentToPoints(m, metrics[m]);
  }
  return out;
}

function computePowerRank(points) {
  const total     = Math.round(Object.values(points).reduce((s, v) => s + v, 0) * 100) / 100;
  const powerRank = Math.round(total / 10 * 100) / 100;
  return { total, powerRank };
}

// ── What-if simulator ─────────────────────────────────────────────────────────

function simulateWhatIf(metrics, changes) {
  const beforePts              = computePoints(metrics);
  const { total: bTotal, powerRank: bRank } = computePowerRank(beforePts);

  const updated                = { ...metrics, ...changes };
  const afterPts               = computePoints(updated);
  const { total: aTotal, powerRank: aRank } = computePowerRank(afterPts);

  const deltas = {};
  for (const m of Object.keys(METRIC_MAX_POINTS)) {
    deltas[m] = Math.round(((afterPts[m] || 0) - (beforePts[m] || 0)) * 100) / 100;
  }

  return {
    before_rank:    bRank,
    after_rank:     aRank,
    rank_delta:     Math.round((aRank - bRank) * 100) / 100,
    before_points:  bTotal,
    after_points:   aTotal,
    points_delta:   Math.round((aTotal - bTotal) * 100) / 100,
    category_deltas: deltas,
  };
}

// ── Path to target rank ───────────────────────────────────────────────────────

function pathToRank(metrics, targetRank) {
  const curPts                 = computePoints(metrics);
  const { total: curTotal, powerRank: curRk } = computePowerRank(curPts);
  const targetTotal            = Math.round(targetRank * 10 * 100) / 100;
  const needed                 = Math.max(0, Math.round((targetTotal - curTotal) * 100) / 100);

  const candidates = [];
  for (const metric of Object.keys(METRIC_MAX_POINTS)) {
    const curPct  = metrics[metric] || 0;
    const curPt   = percentToPoints(metric, curPct);
    const maxPt   = percentToPoints(metric, 125);
    const gain    = Math.round((maxPt - curPt) * 100) / 100;
    if (gain > 0) candidates.push({ metric, current_pct: curPct, current_pts: curPt, max_gain: gain });
  }
  candidates.sort((a, b) => b.max_gain - a.max_gain);

  const actions = [];
  let projected = curTotal;
  for (const c of candidates) {
    if (projected >= targetTotal) break;
    actions.push({ metric: c.metric, current_pct: c.current_pct, points_added: c.max_gain });
    projected = Math.round((projected + c.max_gain) * 100) / 100;
  }

  return {
    current_rank:        curRk,
    current_points:      curTotal,
    target_rank:         targetRank,
    target_points:       targetTotal,
    needed_points:       needed,
    recommended_actions: actions,
    projected_points:    projected,
    projected_rank:      Math.round(projected / 10 * 100) / 100,
  };
}

// ── Commission projection ─────────────────────────────────────────────────────

function commissionTierKey(rank) {
  return rank >= 9.0 ? "rank_9" : "rank_8";
}

function projectCommission(rank, sales) {
  function calc(tierKey) {
    const r = COMMISSION_TIERS[tierKey];
    return Math.round((
      (sales.new_voice_premium    || 0) * r.new_voice_premium
    + (sales.new_voice_extra      || 0) * r.new_voice_extra
    + (sales.new_voice_starter    || 0) * r.new_voice_starter
    + (sales.fiber_aia            || 0) * r.fiber_aia
    + (sales.voice_upgrade        || 0) * r.voice_upgrade
    + (sales.accessories_revenue  || 0) * r.accessories_pct
    + (sales.pa1                  || 0) * r.pa1
    + (sales.pa4                  || 0) * r.pa4
    + (sales.htp                  || 0) * r.htp
    ) * 100) / 100;
  }

  const currentTier = commissionTierKey(rank);
  const currentPay  = calc(currentTier);
  const rank9Pay    = calc("rank_9");

  return {
    current_rank:       rank,
    current_tier:       currentTier,
    current_commission: currentPay,
    rank9_commission:   rank9Pay,
    rank9_uplift:       Math.round((rank9Pay - currentPay) * 100) / 100,
  };
}

// ── Report helper ─────────────────────────────────────────────────────────────

function generateReport(metrics) {
  const pts                   = computePoints(metrics);
  const { total, powerRank }  = computePowerRank(pts);
  const lines = ["Power Rank Report", "=".repeat(42)];
  for (const [m, maxP] of Object.entries(METRIC_MAX_POINTS)) {
    const pct = (metrics[m] || 0).toFixed(1);
    const p   = (pts[m]     || 0).toFixed(2);
    lines.push(`  ${m.padEnd(14)} ${String(pct).padStart(6)}%  →  ${String(p).padStart(5)} / ${maxP} pts`);
  }
  lines.push("-".repeat(42));
  lines.push(`  Total Points:   ${total.toFixed(2)}`);
  lines.push(`  Power Rank:     ${powerRank.toFixed(2)}`);
  return lines.join("\n");
}

// ── CLI example ───────────────────────────────────────────────────────────────

if (require.main === module) {
  const snapshot = {
    opps: 201, ppvga: 237, fiber: 62, aia: 124,
    accessories: 151, protection: 46, rate_plan: 59, next_up: 76,
  };

  console.log(generateReport(snapshot));
  console.log("\nPath to 9.0:");
  console.log(JSON.stringify(pathToRank(snapshot, 9.0), null, 2));

  console.log("\nWhat-if: fiber → 85 %:");
  console.log(JSON.stringify(simulateWhatIf(snapshot, { fiber: 85 }), null, 2));

  const sampleSales = {
    new_voice_premium: 8, new_voice_extra: 4, new_voice_starter: 2,
    fiber_aia: 3, voice_upgrade: 5, accessories_revenue: 350,
    pa1: 6, pa4: 3, htp: 2,
  };
  console.log("\nCommission projection:");
  console.log(JSON.stringify(projectCommission(8.0, sampleSales), null, 2));
}

module.exports = {
  METRIC_MAX_POINTS,
  COMMISSION_TIERS,
  PROTECTION_TABLE,
  RATE_PLAN_TABLE,
  NEXT_UP_TABLE,
  percentToPoints,
  computePoints,
  computePowerRank,
  simulateWhatIf,
  pathToRank,
  commissionTierKey,
  projectCommission,
  generateReport,
};
