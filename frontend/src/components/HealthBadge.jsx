import { ShieldAlert } from 'lucide-react';
import { RECOMMENDATION_STYLE, STATUS_STYLE, recommendationStyle } from '../utils/constants';
import { cx, healthBand, humanise } from '../utils/formatters';

/** Coloured pill showing a 0-100 health score and its band. */
export default function HealthBadge({ score, showBand = true, size = 'md' }) {
  const band = healthBand(score);
  const value = score === null || score === undefined ? '--' : Number(score).toFixed(0);

  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full font-semibold',
        band.badge,
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm',
      )}
      title={`Health score ${value}/100 (${band.label})`}
    >
      <span className="font-mono tabular-nums">{value}</span>
      {showBand ? <span className="text-[0.65rem] uppercase tracking-wide">{band.label}</span> : null}
    </span>
  );
}

/** Horizontal health bar with a numeric read-out. */
export function HealthBar({ score, className = '' }) {
  const band = healthBand(score);
  const width = Math.max(0, Math.min(100, Number(score) || 0));

  return (
    <div className={cx('w-full', className)}>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="font-mono text-sm font-bold tabular-nums text-navy-900">
          {score === null || score === undefined ? '--' : Number(score).toFixed(1)}
          <span className="text-xs font-normal text-steel-500">/100</span>
        </span>
        <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: band.hex }}>
          {band.label}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-steel-200">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${width}%`, backgroundColor: band.hex }}
          role="progressbar"
          aria-valuenow={width}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Health score"
        />
      </div>
    </div>
  );
}

/** Recommendation pill (the four categories, or Defer to Inspection). */
export function RecommendationBadge({ recommendation, size = 'md' }) {
  if (!recommendation) {
    return (
      <span className="badge bg-steel-100 text-steel-500" title="No AI assessment recorded yet">
        Not assessed
      </span>
    );
  }
  const style = recommendationStyle(recommendation) || RECOMMENDATION_STYLE.DISPOSE;
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full font-bold tracking-wide',
        style.badge,
        size === 'sm' ? 'px-2 py-0.5 text-[0.65rem]' : 'px-3 py-1 text-xs',
      )}
      title={style.description}
    >
      <span className={cx('h-1.5 w-1.5 rounded-full', style.dot)} aria-hidden="true" />
      {humanise(recommendation)}
    </span>
  );
}

/** Lifecycle status pill. */
export function StatusBadge({ status, size = 'md' }) {
  return (
    <span
      className={cx(
        'inline-flex items-center rounded-full font-semibold',
        STATUS_STYLE[status] || 'bg-steel-100 text-steel-600',
        size === 'sm' ? 'px-2 py-0.5 text-[0.65rem]' : 'px-2.5 py-0.5 text-xs',
      )}
    >
      {humanise(status)}
    </span>
  );
}

/** Compact marker for safety-critical component types. */
export function SafetyChip({ compact = false, className = '' }) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-full border border-red-300 bg-red-50 font-bold uppercase tracking-wide text-red-700',
        compact ? 'px-1.5 py-0.5 text-[0.6rem]' : 'px-2.5 py-0.5 text-xs',
        className,
      )}
      title="Safety-critical component - mandatory human inspection"
    >
      <ShieldAlert className={compact ? 'h-3 w-3' : 'h-3.5 w-3.5'} aria-hidden="true" />
      {compact ? 'Safety' : 'Safety-critical'}
    </span>
  );
}
