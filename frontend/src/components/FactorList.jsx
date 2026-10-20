import {
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  Minus,
  TriangleAlert,
} from 'lucide-react';
import { IMPACT_STYLE } from '../utils/constants';
import { cx, formatPercent } from '../utils/formatters';

const ICONS = {
  positive: CheckCircle2,
  low: Minus,
  moderate: ArrowUpRight,
  high: CircleAlert,
  critical: TriangleAlert,
};

const ICON_TONES = {
  positive: 'text-emerald-600',
  low: 'text-steel-400',
  moderate: 'text-amber-600',
  high: 'text-orange-600',
  critical: 'text-red-600',
};

/**
 * Ranked explanation factors behind a recommendation.
 *
 * Each row shows the factor, its severity, a plain-language sentence and -
 * optionally - how much the trained model relies on that feature overall.
 */
export default function FactorList({ factors = [], showImportance = true, numbered = true }) {
  if (!factors.length) {
    return <p className="text-sm text-steel-500">No explanation factors were returned.</p>;
  }

  return (
    <ol className="space-y-3">
      {factors.map((factor, index) => {
        const impact = factor.impact || 'low';
        const Icon = ICONS[impact] || Minus;
        const style = IMPACT_STYLE[impact] || IMPACT_STYLE.low;

        return (
          <li
            key={`${factor.factor}-${index}`}
            className="flex gap-3 rounded-lg border border-steel-200 bg-white p-3"
          >
            {numbered ? (
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-navy-800 text-xs font-bold text-white">
                {index + 1}
              </span>
            ) : null}

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Icon className={cx('h-4 w-4 shrink-0', ICON_TONES[impact])} aria-hidden="true" />
                <span className="text-sm font-semibold text-navy-900">{factor.factor}</span>
                <span className={cx('badge', style.badge)}>{style.label} impact</span>
                {factor.value !== undefined && factor.value !== null ? (
                  <span className="font-mono text-xs text-steel-500">
                    {Number(factor.value).toLocaleString()} {factor.unit}
                  </span>
                ) : null}
              </div>

              <p className="mt-1 text-sm text-steel-600">{factor.description}</p>

              {showImportance && factor.model_importance ? (
                <div className="mt-2 flex items-center gap-2">
                  <span className="text-[0.65rem] uppercase tracking-wide text-steel-400">
                    Model importance
                  </span>
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-steel-200">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{ width: `${Math.min(100, factor.model_importance * 300)}%` }}
                    />
                  </div>
                  <span className="font-mono text-[0.65rem] text-steel-500">
                    {formatPercent(factor.model_importance, 1)}
                  </span>
                </div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Per-prediction SHAP (Shapley value) attribution - a second, independent
 * explanation method from the blended factors in `FactorList`. Bars point
 * right (red) when a feature pushed toward a worse disposition and left
 * (green) when it pushed toward a better one.
 */
export function ShapFactorList({ factors = [] }) {
  if (!factors?.length) {
    return <p className="text-sm text-steel-500">SHAP attribution was not computed for this assessment.</p>;
  }
  const maxAbs = Math.max(...factors.map((factor) => Math.abs(factor.shap_value)), 0.0001);

  return (
    <ol className="space-y-2">
      {factors.map((factor) => {
        const magnitude = Math.min(100, (Math.abs(factor.shap_value) / maxAbs) * 100);
        const worsens = factor.direction === 'increases_risk';
        return (
          <li key={factor.feature} className="flex items-center gap-3 rounded-lg border border-steel-200 bg-white p-2.5">
            <span className="w-40 shrink-0 truncate text-xs font-medium text-steel-700">{factor.factor}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-steel-200">
              <div
                className={cx('h-full rounded-full', worsens ? 'bg-orange-500' : 'bg-emerald-500')}
                style={{ width: `${magnitude}%` }}
              />
            </div>
            <span
              className={cx(
                'w-24 shrink-0 text-right font-mono text-[0.65rem]',
                worsens ? 'text-orange-700' : 'text-emerald-700',
              )}
            >
              {worsens ? 'worse' : 'better'} {factor.shap_value.toFixed(3)}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** Weighted breakdown of the transparent health score. */
export function HealthBreakdown({ breakdown = [], limit = 6 }) {
  if (!breakdown.length) return null;
  const rows = breakdown.slice(0, limit);
  const maxContribution = Math.max(...rows.map((row) => row.contribution), 0.0001);

  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={row.factor} className="flex items-center gap-3">
          <span className="w-44 shrink-0 truncate text-xs font-medium text-steel-600">
            {row.factor.replace(/_/g, ' ')}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-steel-200">
            <div
              className="h-full rounded-full bg-navy-500"
              style={{ width: `${(row.contribution / maxContribution) * 100}%` }}
            />
          </div>
          <span className="w-24 shrink-0 text-right font-mono text-xs tabular-nums text-steel-500">
            -{row.penalty_points.toFixed(1)} pts
          </span>
          <span className="hidden w-16 shrink-0 text-right font-mono text-[0.65rem] text-steel-400 sm:inline">
            w={row.weight.toFixed(2)}
          </span>
        </div>
      ))}
      <p className="pt-1 text-[0.65rem] text-steel-400">
        <ArrowDownRight className="mr-1 inline h-3 w-3" aria-hidden="true" />
        Penalty points deducted from 100. Weights are fixed and documented in the health-score
        methodology.
      </p>
    </div>
  );
}
