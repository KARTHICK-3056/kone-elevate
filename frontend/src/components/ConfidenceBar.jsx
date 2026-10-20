import { recommendationStyle } from '../utils/constants';
import { cx, formatPercent, humanise } from '../utils/formatters';

/**
 * Model-confidence meter.
 *
 * The colour communicates how much weight a technician should give the
 * recommendation: low confidence is a prompt for human judgement, never a
 * reason to hide the prediction.
 */
export default function ConfidenceBar({ confidence, showScale = true, className = '' }) {
  const value = Math.max(0, Math.min(1, Number(confidence) || 0));
  const percent = value * 100;

  let tone = { color: '#d93025', label: 'Low confidence' };
  if (value >= 0.85) tone = { color: '#0f9d58', label: 'High confidence' };
  else if (value >= 0.7) tone = { color: '#34a853', label: 'Good confidence' };
  else if (value >= 0.55) tone = { color: '#f4a300', label: 'Moderate confidence' };

  return (
    <div className={cx('w-full', className)}>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-steel-500">
          Model confidence
        </span>
        <span className="font-mono text-sm font-bold tabular-nums" style={{ color: tone.color }}>
          {formatPercent(value, 1)}
        </span>
      </div>

      <div className="h-2.5 w-full overflow-hidden rounded-full bg-steel-200">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${percent}%`, backgroundColor: tone.color }}
          role="progressbar"
          aria-valuenow={Math.round(percent)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Model confidence"
        />
      </div>

      {showScale ? (
        <div className="mt-1 flex items-center justify-between text-[0.65rem] text-steel-400">
          <span>0%</span>
          <span className="font-medium" style={{ color: tone.color }}>
            {tone.label}
          </span>
          <span>100%</span>
        </div>
      ) : null}
    </div>
  );
}

/** Probability bars for the four recommendation categories. */
export function ProbabilityBreakdown({ probabilities = {}, className = '' }) {
  const entries = Object.entries(probabilities).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;


  return (
    <div className={cx('space-y-2', className)}>
      <p className="text-xs font-semibold uppercase tracking-wide text-steel-500">
        Class probabilities
      </p>
      {entries.map(([label, probability]) => (
        <div key={label} className="flex items-center gap-3">
          <span className="w-44 shrink-0 text-xs font-semibold text-steel-600">{humanise(label)}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-steel-200">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.max(1, probability * 100)}%`,
                backgroundColor: recommendationStyle(label)?.hex || '#8593aa',
              }}
            />
          </div>
          <span className="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-steel-600">
            {formatPercent(probability, 1)}
          </span>
        </div>
      ))}
    </div>
  );
}
