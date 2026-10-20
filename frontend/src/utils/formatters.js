/** Display formatting helpers shared across the UI. */

import { GRADE_NOT_DETERMINED, HEALTH_BANDS, recommendationLabel } from './constants';

const NUMBER = new Intl.NumberFormat('en-IN');
const COMPACT = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 });

/** Format an integer-ish number with thousands separators. */
export function formatNumber(value, fallback = '-') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
  return NUMBER.format(Math.round(Number(value)));
}

/** Format a number with a fixed number of decimals. */
export function formatDecimal(value, digits = 1, fallback = '-') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
  return Number(value).toFixed(digits);
}

/** Compact form for dashboard tiles: 1.2M, 84K, ... */
export function formatCompact(value, fallback = '-') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
  return COMPACT.format(Number(value));
}

/**
 * Format a prototype currency estimate.
 * The symbol is supplied by the backend so the constant stays configurable.
 */
export function formatCurrency(value, symbol = 'Rs.', { compact = true } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  const amount = Number(value);
  if (compact && Math.abs(amount) >= 100000) return `${symbol} ${COMPACT.format(amount)}`;
  return `${symbol} ${NUMBER.format(Math.round(amount))}`;
}

/** Format a 0-1 probability as a percentage string. */
export function formatPercent(value, digits = 0, fallback = '-') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

/** Format an already-0-100 value as a percentage string. */
export function formatPercentPoints(value, digits = 0, fallback = '-') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
  return `${Number(value).toFixed(digits)}%`;
}

/** ISO date/datetime to `12 Apr 2018`. */
export function formatDate(value, fallback = '-') {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** ISO datetime to `12 Apr 2018, 14:05`. */
export function formatDateTime(value, fallback = '-') {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return `${date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })}, ${date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`;
}

/** Relative age, e.g. `3 days ago`. */
export function formatRelative(value, fallback = '-') {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;

  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} month${months === 1 ? '' : 's'} ago`;
  return `${Math.floor(months / 12)} year${Math.floor(months / 12) === 1 ? '' : 's'} ago`;
}

/** Component age in years, e.g. `5.2 yrs`. */
export function formatAge(years, fallback = '-') {
  if (years === null || years === undefined || Number.isNaN(Number(years))) return fallback;
  return `${Number(years).toFixed(1)} yrs`;
}

/**
 * `UNDER_INSPECTION` -> `Under Inspection`. A recommendation code gets its
 * exact category name (`CONTINUE_USING` -> `Continue Using – No Changes
 * Required`), legacy codes included.
 */
export function humanise(value, fallback = '-') {
  if (!value) return fallback;
  const label = recommendationLabel(String(value));
  if (label) return label;
  return String(value)
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

/**
 * `Cast Iron - Grade: <label>`. The label comes from the API: the recorded
 * grade, or the industry-standard grade marked "(industry standard - assumed,
 * not recorded)". Not Determined only when no grade is catalogued.
 */
export function materialWithGrade(material, gradeLabel) {
  if (!material) return '-';
  return `${material} - Grade: ${gradeLabel || GRADE_NOT_DETERMINED}`;
}

/** Truncate a hash for display: `a1b2c3d4...9f8e7d6c`. */
export function shortHash(hash, head = 8, tail = 6) {
  if (!hash) return '-';
  if (hash.length <= head + tail + 3) return hash;
  return `${hash.slice(0, head)}...${hash.slice(-tail)}`;
}

/** Return the health band descriptor for a 0-100 score. */
export function healthBand(score) {
  if (score === null || score === undefined || Number.isNaN(Number(score))) {
    return { min: 0, label: 'NOT ASSESSED', hex: '#8593aa', badge: 'bg-steel-100 text-steel-600' };
  }
  return HEALTH_BANDS.find((band) => Number(score) >= band.min) ?? HEALTH_BANDS[HEALTH_BANDS.length - 1];
}

/** Small helper for conditional class names (avoids a clsx dependency). */
export function cx(...values) {
  return values.filter(Boolean).join(' ');
}

/** Trigger a browser download for a text/CSV blob. */
export function downloadBlob(content, filename, type = 'text/csv;charset=utf-8;') {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
