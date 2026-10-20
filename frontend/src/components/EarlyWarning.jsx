import { useState } from 'react';
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlarmClock, Check, ChevronDown, ChevronUp, Radar, Wrench, X } from 'lucide-react';
import { cx, formatDate } from '../utils/formatters';

/**
 * Pre-emptive issue forecast, backed by `app.ml.early_warning`.
 *
 * Pre-analysis rather than post-analysis: which problem the component is
 * heading towards, when, what to do before then, and the evidence and
 * independent signals behind each prediction.
 */

const URGENCY = {
  PRESENT: { label: 'Limit already crossed', chip: 'bg-red-600 text-white', border: 'border-red-300' },
  ACT_NOW: { label: 'Act now', chip: 'bg-red-100 text-red-800', border: 'border-red-200' },
  WITHIN_A_YEAR: { label: 'Within a year', chip: 'bg-amber-100 text-amber-900', border: 'border-amber-200' },
  PLAN_AHEAD: { label: 'Plan ahead', chip: 'bg-sky-100 text-sky-900', border: 'border-sky-200' },
};

const CONFIDENCE = {
  HIGH: 'bg-emerald-100 text-emerald-800',
  MEDIUM: 'bg-amber-100 text-amber-900',
  LOW: 'bg-steel-100 text-steel-700',
};

const INDICATOR_STATUS = {
  worsening: { label: 'Worsening - issue predicted', tone: 'text-amber-700' },
  exceeded: { label: 'Limit crossed', tone: 'text-red-700' },
  worsening_beyond_horizon: { label: 'Slowly worsening - beyond 3 yr', tone: 'text-steel-600' },
  stable: { label: 'Stable', tone: 'text-emerald-700' },
  insufficient_history: { label: 'Too few readings to trend', tone: 'text-steel-400' },
};

const when = (issue) => {
  if (issue.present) return 'now';
  const months = Math.max(1, Math.round(issue.days_until / 30.4));
  return months >= 24 ? `in ~${(months / 12).toFixed(1)} yr` : `in ~${months} mo`;
};

function tone(forecast) {
  const issues = forecast.issues || [];
  if (issues.some((i) => i.present || i.urgency === 'ACT_NOW')) return 'border-red-200 bg-red-50 text-red-900';
  if (issues.some((i) => i.urgency === 'WITHIN_A_YEAR')) return 'border-amber-200 bg-amber-50 text-amber-900';
  if (issues.length) return 'border-sky-200 bg-sky-50 text-sky-900';
  return 'border-emerald-200 bg-emerald-50 text-emerald-900';
}

/* -------------------------------------------------------------------------- */
/* Indication shown right after an AI assessment                              */
/* -------------------------------------------------------------------------- */
export function EarlyWarningIndicator({ forecast }) {
  const [open, setOpen] = useState(false);
  if (!forecast?.supported) return null;
  const issues = forecast.issues || [];

  return (
    <div className={cx('rounded-lg border px-4 py-3', tone(forecast))} role="status">
      <div className="flex items-start gap-2.5">
        <Radar className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold uppercase tracking-wide">Pre-emptive issue forecast</p>
          <p className="mt-0.5 text-sm font-semibold">{forecast.headline}</p>
          {issues.length ? (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {issues.map((issue) => (
                <li
                  key={issue.code}
                  className={cx('badge', URGENCY[issue.urgency]?.chip)}
                  title={issue.why}
                >
                  {issue.title} - {when(issue)}
                </li>
              ))}
            </ul>
          ) : null}
          {issues.length ? (
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold underline-offset-2 hover:underline"
              aria-expanded={open}
            >
              {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              {open ? 'Hide' : 'Show'} evidence, justification and measures
            </button>
          ) : null}
        </div>
      </div>
      {open ? (
        <div className="mt-3 text-steel-800">
          <EarlyWarningPanel forecast={forecast} />
        </div>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Full forecast card for the component and passport pages                    */
/* -------------------------------------------------------------------------- */
export function EarlyWarningCard({ forecast }) {
  if (!forecast) return null;
  return (
    <section className="card" id="early-warning">
      <header className="card-header">
        <div>
          <h2 className="card-title">Pre-emptive issue forecast</h2>
          <p className="mt-0.5 text-xs text-steel-500">
            Predicted before it arrives - with evidence, justification and measures
          </p>
        </div>
        <Radar className="h-5 w-5 text-steel-400" aria-hidden="true" />
      </header>
      <div className="card-body space-y-4">
        {forecast.supported ? (
          <>
            <div className={cx('rounded-lg border px-4 py-3 text-sm font-semibold', tone(forecast))}>
              {forecast.headline}
            </div>
            <EarlyWarningPanel forecast={forecast} />
          </>
        ) : (
          <p className="text-sm text-steel-500">{forecast.reason}</p>
        )}
      </div>
    </section>
  );
}

export function EarlyWarningPanel({ forecast }) {
  return (
    <div className="space-y-4">
      {forecast.issues.map((issue) => (
        <IssueCard key={issue.code} issue={issue} />
      ))}
      <IndicatorTable indicators={forecast.indicators} />
      <p className="text-[0.7rem] leading-relaxed text-steel-500">
        {forecast.method} Lead time allowed for planning and parts:{' '}
        {forecast.lead_time_days} days.
      </p>
    </div>
  );
}

function IssueCard({ issue }) {
  const urgency = URGENCY[issue.urgency] || URGENCY.PLAN_AHEAD;
  return (
    <article className={cx('rounded-lg border bg-white', urgency.border)}>
      <header className="flex flex-wrap items-start justify-between gap-2 border-b border-steel-100 px-4 py-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={cx('badge', urgency.chip)}>{urgency.label}</span>
            <span className={cx('badge', CONFIDENCE[issue.confidence_label])}>
              {issue.confidence_label} confidence ({Math.round(issue.confidence * 100)}%)
            </span>
            {issue.safety_critical ? (
              <span className="badge bg-red-50 text-red-700">Safety-critical</span>
            ) : null}
          </div>
          <h3 className="mt-1.5 text-sm font-bold text-navy-900">{issue.title}</h3>
          <p className="text-xs text-steel-500">{issue.mechanism}</p>
        </div>
        <div className="text-right text-xs">
          <p className="flex items-center justify-end gap-1 font-semibold text-navy-900">
            <AlarmClock className="h-3.5 w-3.5" aria-hidden="true" />
            {issue.present ? 'Present now' : `Expected ${formatDate(issue.predicted_date)}`}
          </p>
          <p className="text-steel-600">
            Act by <strong>{formatDate(issue.act_by)}</strong>
          </p>
        </div>
      </header>

      <div className="grid gap-4 px-4 py-3 lg:grid-cols-2">
        <div className="space-y-3">
          <div>
            <p className="label-caps">Why we predict this</p>
            <p className="text-xs text-steel-700">{issue.why}</p>
            <p className="mt-0.5 text-[0.7rem] text-steel-400">Primary evidence: {issue.primary_evidence}</p>
          </div>
          <Evidence evidence={issue.evidence} />
        </div>

        <div className="space-y-3">
          <div>
            <p className="label-caps">Independent signals checked</p>
            <ul className="space-y-1.5">
              {issue.justification.map((signal) => (
                <li key={signal.signal} className="flex gap-2 text-xs">
                  {signal.agrees ? (
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" aria-label="agrees" />
                  ) : (
                    <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-steel-400" aria-label="does not agree" />
                  )}
                  <span>
                    <strong className="text-navy-900">{signal.signal}.</strong>{' '}
                    <span className="text-steel-600">{signal.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="label-caps">Recommended measures before it arrives</p>
            <ul className="space-y-1">
              {issue.measures.map((measure) => (
                <li key={measure} className="flex gap-2 text-xs text-steel-700">
                  <Wrench className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" aria-hidden="true" />
                  {measure}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </article>
  );
}

function Evidence({ evidence }) {
  if (evidence.kind === 'life') {
    return (
      <div>
        <p className="label-caps">Evidence - usage-adjusted life</p>
        <p className="text-xs text-steel-600">
          {Math.round(evidence.life_consumed * 100)}% of a {evidence.design_life_years.toFixed(1)}-year
          adjusted design life used, ageing at {evidence.ageing_rate.toFixed(2)}x design.
        </p>
        <ul className="mt-1 flex flex-wrap gap-1.5">
          {evidence.factors.map((factor) => (
            <li
              key={factor.label}
              className={cx(
                'badge',
                factor.multiplier > 1.02
                  ? 'bg-red-50 text-red-700'
                  : factor.multiplier < 0.98
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-steel-100 text-steel-600',
              )}
            >
              {factor.label} x{factor.multiplier.toFixed(2)}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  return <TrendChart evidence={evidence} />;
}

function TrendChart({ evidence }) {
  const time = (iso) => new Date(iso).getTime();
  const rows = [
    ...evidence.readings.map((r) => ({ t: time(r.date), reading: r.value })),
    ...evidence.fit.map((f) => ({ t: time(f.date), fit: f.value })),
  ].sort((a, b) => a.t - b.t);
  const values = rows.flatMap((r) => [r.reading, r.fit]).filter((v) => v != null);
  const low = Math.min(evidence.limit, ...values);
  const high = Math.max(evidence.limit, ...values);
  const pad = (high - low) * 0.15 || 1;
  const today = Date.now();
  const firstYear = new Date(rows[0].t).getFullYear() + 1;
  const lastYear = new Date(rows[rows.length - 1].t).getFullYear();
  const step = Math.max(1, Math.ceil((lastYear - firstYear + 1) / 6));
  const ticks = [];
  for (let y = firstYear; y <= lastYear; y += step) ticks.push(new Date(y, 0, 1).getTime());

  return (
    <div>
      <p className="label-caps">
        Evidence - {evidence.label.toLowerCase()} trend (R&sup2; {evidence.r2.toFixed(2)})
      </p>
      <div style={{ height: 170 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              ticks={ticks}
              tickFormatter={(t) => new Date(t).getFullYear()}
              stroke="#8593aa"
              fontSize={10}
            />
            <YAxis domain={[Math.floor(low - pad), Math.ceil(high + pad)]} stroke="#8593aa" fontSize={10} />
            <Tooltip
              labelFormatter={(t) => formatDate(new Date(t).toISOString())}
              formatter={(v, name) => [`${Number(v).toFixed(2)} ${evidence.unit}`, name]}
              contentStyle={{ borderRadius: '0.5rem', fontSize: '0.75rem' }}
            />
            <ReferenceLine
              y={evidence.limit}
              stroke="#d93025"
              strokeDasharray="4 4"
              label={{ value: `Limit ${evidence.limit}`, position: 'insideTopRight', fontSize: 10, fill: '#d93025' }}
            />
            <ReferenceLine x={today} stroke="#0aa2c0" label={{ value: 'Today', position: 'top', fontSize: 10, fill: '#077f97' }} />
            <Line
              dataKey="reading"
              name="Recorded reading"
              stroke="#0f1c33"
              strokeWidth={0}
              dot={{ r: 3, fill: '#0f1c33' }}
              isAnimationActive={false}
            />
            <Line
              dataKey="fit"
              name="Trend, extrapolated"
              stroke="#f4a300"
              strokeDasharray="6 3"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[0.7rem] text-steel-500">
        Dots are recorded service readings; the dashed line is the fitted trend extended to where it
        meets the limit.
      </p>
    </div>
  );
}

function IndicatorTable({ indicators = [] }) {
  if (!indicators.length) return null;
  return (
    <div>
      <p className="label-caps">Every indicator monitored</p>
      <div className="overflow-x-auto rounded-lg border border-steel-200">
        <table className="w-full min-w-[520px] text-left text-xs">
          <thead className="bg-steel-50 text-[0.65rem] uppercase tracking-wide text-steel-500">
            <tr>
              <th className="px-3 py-2">Indicator</th>
              <th className="px-3 py-2">Foreshadows</th>
              <th className="px-3 py-2">Trend</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-steel-100">
            {indicators.map((row) => {
              const status = INDICATOR_STATUS[row.status] || { label: row.status, tone: '' };
              return (
                <tr key={row.indicator}>
                  <td className="px-3 py-2 font-semibold text-navy-900">
                    {row.label}
                    <span className="block text-[0.65rem] font-normal text-steel-400">
                      limit {row.limit} {row.unit} - {row.points} readings
                    </span>
                  </td>
                  <td className="px-3 py-2 text-steel-600">{row.issue}</td>
                  <td className="px-3 py-2 font-mono text-steel-600">
                    {row.slope_per_year != null
                      ? `${row.slope_per_year > 0 ? '+' : ''}${row.slope_per_year} ${row.unit}/yr (R² ${row.r2})`
                      : '-'}
                  </td>
                  <td className={cx('px-3 py-2 font-semibold', status.tone)}>
                    {status.label}
                    {row.years_until != null && row.status !== 'exceeded'
                      ? ` (${row.years_until} yr)`
                      : ''}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
