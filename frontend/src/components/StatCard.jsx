import { Link } from 'react-router-dom';
import { ArrowUpRight, Info } from 'lucide-react';
import { cx } from '../utils/formatters';

const TONES = {
  default: { icon: 'bg-steel-100 text-steel-600', accent: 'border-steel-200' },
  navy: { icon: 'bg-navy-100 text-navy-700', accent: 'border-navy-200' },
  accent: { icon: 'bg-cyan-100 text-cyan-700', accent: 'border-cyan-200' },
  continue: { icon: 'bg-emerald-100 text-emerald-700', accent: 'border-emerald-200' },
  component: { icon: 'bg-blue-100 text-blue-700', accent: 'border-blue-200' },
  material: { icon: 'bg-amber-100 text-amber-800', accent: 'border-amber-200' },
  dispose: { icon: 'bg-red-100 text-red-700', accent: 'border-red-200' },
  warning: { icon: 'bg-orange-100 text-orange-700', accent: 'border-orange-200' },
};

/**
 * Dashboard KPI tile.
 *
 * `estimate` renders the mandatory "Prototype estimate" caption for any value
 * derived from the configurable impact constants.
 */
export default function StatCard({
  label,
  value,
  unit,
  hint,
  icon: Icon,
  tone = 'default',
  to,
  estimate = false,
  loading = false,
  footer,
}) {
  const palette = TONES[tone] || TONES.default;

  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-steel-500">{label}</p>
        {Icon ? (
          <span className={cx('rounded-lg p-2', palette.icon)}>
            <Icon className="h-4 w-4" aria-hidden="true" />
          </span>
        ) : null}
      </div>

      <div className="mt-3 flex items-baseline gap-1.5">
        {loading ? (
          <span className="skeleton h-8 w-24" />
        ) : (
          <>
            <span className="stat-value">{value}</span>
            {unit ? <span className="text-sm font-medium text-steel-500">{unit}</span> : null}
          </>
        )}
      </div>

      {hint ? <p className="mt-1 text-xs text-steel-500">{hint}</p> : null}

      {estimate ? (
        <p className="mt-2 inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-[0.65rem] font-medium text-amber-800">
          <Info className="h-3 w-3" aria-hidden="true" />
          Prototype estimate
        </p>
      ) : null}

      {footer}

      {to ? (
        <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-accent">
          View <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
      ) : null}
    </>
  );

  const className = cx(
    'card border-l-4 p-5 transition-shadow',
    palette.accent,
    to && 'hover:shadow-elevated',
  );

  if (to) {
    return (
      <Link to={to} className={cx(className, 'block')}>
        {body}
      </Link>
    );
  }

  return <div className={className}>{body}</div>;
}
