"use strict";

const fs = require("fs");

const THRESHOLDS = [125, 100, 90, 80, 70, 60, 50, 40, 30, 20, 0];

const METRIC_MAX_POINTS = {
  opps_pct: 10,
  ppvga_pct: 30,
  internet_pct: 20,
  accessories_pct: 10,
  protection_pct: 5,
  rate_plan_pct: 5,
  next_up_pct: 5,
  event_opps_pct: 5,
  plus1_pct: 5,
  csat_pct: 5,
};

const DEFAULT_MULTIPLIERS = {
  125: 1.0,
  100: 1.0,
  90: 0.9,
  80: 0.8,
  70: 0.7,
  60: 0.6,
  50: 0.5,
  40: 0.4,
  30: 0.3,
  20: 0.2,
  0: 0.0,
};

const FIVE_POINT_MULTIPLIERS = {
  125: 1.0,
  100: 1.0,
  90: 1.0,
  80: 1.0,
  70: 0.8,
  60: 0.6,
  50: 0.4,
  40: 0.2,
  30: 0.0,
  20: 0.0,
  0: 0.0,
};

const METRIC_RULES = {
  protection_pct: { multipliers: FIVE_POINT_MULTIPLIERS, allowBelow50: false },
  rate_plan_pct: { multipliers: FIVE_POINT_MULTIPLIERS, allowBelow50: false },
  next_up_pct: { multipliers: FIVE_POINT_MULTIPLIERS, allowBelow50: false },
  event_opps_pct: { multipliers: FIVE_POINT_MULTIPLIERS, allowBelow50: false },
  plus1_pct: { multipliers: FIVE_POINT_MULTIPLIERS, allowBelow50: false },
  csat_pct: { multipliers: FIVE_POINT_MULTIPLIERS, allowBelow50: false },
};

function toFloat(value, fieldName, errors) {
  if (value === undefined || value === null || value === "") {
    errors.push(`Missing value for ${fieldName}.`);
    return null;
  }
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    errors.push(`Invalid number for ${fieldName}: ${JSON.stringify(value)}.`);
    return null;
  }
  return parsed;
}

function parseCsv(filepath) {
  const content = fs.readFileSync(filepath, "utf8");
  const lines = content.split(/\r?\n/).filter((line) => line.trim() !== "");
  if (lines.length === 0) {
    return [];
  }

  const headers = lines[0].split(",").map((header) => header.trim());
  const records = [];

  for (let i = 1; i < lines.length; i += 1) {
    const values = lines[i].split(",");
    const row = {};
    headers.forEach((header, index) => {
      row[header] = values[index] !== undefined ? values[index].trim() : "";
    });

    const errors = [];
    const dateValue = (row.date || "").trim();
    if (!dateValue) {
      errors.push("Missing date value.");
    }

    const data = {};
    Object.keys(METRIC_MAX_POINTS).forEach((field) => {
      data[field] = toFloat(row[field], field, errors);
    });
    data.htp_pct = toFloat(row.htp_pct, "htp_pct", errors);

    records.push({ date: dateValue, data, errors });
  }

  return records;
}

function percentToPoints(metricName, percent) {
  if (percent === null || percent === undefined) {
    return 0;
  }
  const maxPoints = METRIC_MAX_POINTS[metricName];
  if (maxPoints === undefined) {
    throw new Error(`Unknown metric: ${metricName}`);
  }

  const rules = METRIC_RULES[metricName] || {};
  const multipliers = rules.multipliers || DEFAULT_MULTIPLIERS;
  const allowBelow50 = rules.allowBelow50 || false;

  if (percent < 50 && !allowBelow50) {
    return 0;
  }

  for (const threshold of THRESHOLDS) {
    if (percent >= threshold) {
      const multiplier = Number(multipliers[threshold] || 0);
      return Math.round(maxPoints * multiplier * 100) / 100;
    }
  }

  return 0;
}

function computePoints(record) {
  const points = {};
  Object.keys(METRIC_MAX_POINTS).forEach((metric) => {
    const pointsKey = metric.replace("_pct", "_points");
    points[pointsKey] = percentToPoints(metric, record.data[metric]);
  });

  if (record.data.htp_pct !== null && record.data.htp_pct < 6.5) {
    points.protection_points = Math.round((points.protection_points || 0) / 2 * 100) / 100;
  }

  return points;
}

function computePowerRank(pointsDict) {
  const totalPoints = Math.round(Object.values(pointsDict).reduce((sum, value) => sum + value, 0) * 100) / 100;
  const powerRank = Math.round((totalPoints / 100) * 10 * 100) / 100;
  return { totalPoints, powerRank };
}

function neededToTarget(currentValue, goal, dayOfMonth, daysInMonth, targetPct) {
  if (daysInMonth <= 0) {
    throw new Error("daysInMonth must be greater than zero.");
  }
  const dailyTarget = goal / daysInMonth;
  const neededByToday = dailyTarget * dayOfMonth * (targetPct / 100);
  return Math.max(0, Math.ceil(neededByToday - currentValue));
}

function generateReport(record, points, powerRank) {
  const totalPoints = Math.round(Object.values(points).reduce((sum, value) => sum + value, 0) * 100) / 100;
  const lines = [
    `Date: ${record.date}`,
    "Metric Summary:",
  ];

  Object.keys(METRIC_MAX_POINTS).forEach((metric) => {
    const percentValue = record.data[metric];
    const pointsKey = metric.replace("_pct", "_points");
    const pointsValue = points[pointsKey] || 0;
    const percentDisplay = percentValue === null || percentValue === undefined
      ? "n/a"
      : `${percentValue.toFixed(2)}%`;
    lines.push(`- ${metric}: ${percentDisplay} -> ${pointsValue.toFixed(2)} pts`);
  });

  if (record.errors && record.errors.length > 0) {
    lines.push("Errors:");
    record.errors.forEach((error) => lines.push(`- ${error}`));
  }

  lines.push(`Total Points: ${totalPoints.toFixed(2)}`);
  lines.push(`Power Rank: ${powerRank.toFixed(2)}`);

  return lines.join("\n");
}

function calculateNeededByDate(goals, current, dayOfMonth, daysInMonth, targetRank) {
  const currentRecord = { data: { ...current }, date: "", errors: [] };
  const currentPoints = computePoints(currentRecord);
  const { totalPoints: currentTotal } = computePowerRank(currentPoints);

  const targetPoints = (targetRank / 10) * 100;
  const shortfall = Math.max(0, Math.round((targetPoints - currentTotal) * 100) / 100);

  const recommendations = [];

  Object.keys(METRIC_MAX_POINTS).forEach((metric) => {
    const currentValue = current[metric] || 0;
    const goalValue = goals[metric];
    if (goalValue === undefined) {
      return;
    }

    const currentPercent = goalValue ? (currentValue / goalValue) * 100 : 0;
    const currentMetricPoints = percentToPoints(metric, currentPercent);

    const rules = METRIC_RULES[metric] || {};
    const allowBelow50 = rules.allowBelow50 || false;

    let nextThreshold = null;
    for (const threshold of THRESHOLDS) {
      if (threshold <= currentPercent) {
        continue;
      }
      if (threshold < 50 && !allowBelow50) {
        continue;
      }
      nextThreshold = threshold;
      break;
    }

    if (nextThreshold === null) {
      return;
    }

    const nextPoints = percentToPoints(metric, nextThreshold);
    const pointGain = Math.round(Math.max(0, nextPoints - currentMetricPoints) * 100) / 100;
    if (pointGain <= 0) {
      return;
    }

    const requiredMore = neededToTarget(
      currentValue,
      goalValue,
      dayOfMonth,
      daysInMonth,
      nextThreshold
    );

    recommendations.push({
      metric,
      current_percent: Math.round(currentPercent * 100) / 100,
      next_threshold: nextThreshold,
      point_gain: pointGain,
      needed_more_by_today: requiredMore,
    });
  });

  recommendations.sort((a, b) => b.point_gain - a.point_gain);

  return {
    target_rank: targetRank,
    target_points: Math.round(targetPoints * 100) / 100,
    current_points: currentTotal,
    shortfall_points: shortfall,
    recommendations,
  };
}

if (require.main === module) {
  const sampleRecord = {
    date: "2026-02-14",
    data: {
      opps_pct: 61,
      ppvga_pct: 35,
      internet_pct: 36,
      accessories_pct: 70,
      protection_pct: 83,
      rate_plan_pct: 100,
      next_up_pct: 82,
      event_opps_pct: 40,
      plus1_pct: 38,
      csat_pct: 75,
      htp_pct: 5.1,
    },
    errors: [],
  };

  const points = computePoints(sampleRecord);
  const { totalPoints, powerRank } = computePowerRank(points);
  points.total_points = totalPoints;
  points.power_rank = powerRank;
  console.log(JSON.stringify(points, null, 2));
}

module.exports = {
  parseCsv,
  percentToPoints,
  computePoints,
  computePowerRank,
  neededToTarget,
  generateReport,
  calculateNeededByDate,
};
