import { Link } from 'react-router-dom';
import { Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { FlaskConical, Trash2 } from 'lucide-react';
import { formatDate, formatDateTime } from '../utils/formatters';

/**
 * Saved SIMULATED scenarios for one component.
 *
 * Every scenario is a what-if started from the component's real record. The
 * card says so on every item: simulated projections sit on the passport so
 * they can be discussed, never so they can be mistaken for measurements.
 */
export default function ScenarioCard({ componentId, scenarios = [], onDelete, allowSimulate = true }) {
  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">Simulated scenarios</h2>
          <p className="mt-0.5 text-xs text-steel-500">
            What-ifs run from this component&apos;s real record. Not measurements, not fleet data.
          </p>
        </div>
        <FlaskConical className="h-5 w-5 text-violet-500" aria-hidden="true" />
      </header>
      <div className="card-body space-y-3">
        {scenarios.length ? (
          scenarios.map((scenario) => (
            <ScenarioItem key={scenario.id} scenario={scenario} onDelete={onDelete} />
          ))
        ) : (
          <p className="text-sm text-steel-500">No scenarios saved for this component yet.</p>
        )}
        {allowSimulate && componentId ? (
          <Link to={`/simulation?component=${encodeURIComponent(componentId)}`} className="btn-secondary btn-sm">
            <FlaskConical className="h-4 w-4" aria-hidden="true" />
            Simulate this component
          </Link>
        ) : null}
      </div>
    </section>
  );
}

function ScenarioItem({ scenario, onDelete }) {
  const summary = scenario.summary;
  const first = summary.first_replacement;
  const data = summary.series.map((point) => ({
    year: point.month / 12,
    estimated: Math.round(point.estimated * 1000) / 10,
  }));
  const life = summary.end_state?.life;
  const loadChange = summary.final_load_kg - (summary.historical_load_kg ?? summary.final_load_kg);

  return (
    <article className="rounded-lg border border-violet-200 bg-violet-50/40 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="badge bg-violet-600 text-white">Simulation</span>
            <h3 className="text-sm font-bold text-navy-900">{scenario.name}</h3>
          </div>
          <p className="mt-0.5 text-xs text-steel-600">
            {summary.final_load_kg.toFixed(0)} kg average load
            {summary.historical_load_kg != null
              ? ` (record implies ${summary.historical_load_kg.toFixed(0)} kg, ${loadChange >= 0 ? '+' : ''}${loadChange.toFixed(0)} kg)`
              : ''}{' '}
            - {(summary.months_simulated / 12).toFixed(1)} years from {formatDate(summary.start_date)}
          </p>
        </div>
        {onDelete ? (
          <button
            type="button"
            className="btn-ghost btn-sm text-steel-500"
            onClick={() => onDelete(scenario.id)}
            aria-label={`Delete scenario ${scenario.name}`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        ) : null}
      </div>

      <div className="mt-2 grid gap-3 sm:grid-cols-3">
        <div className="text-xs">
          <p className="label-caps">Outcome</p>
          {first ? (
            <p className="text-navy-900">
              {first.kind === 'breakdown' ? 'Breakdown' : 'Replaced before failure'} on{' '}
              <strong>{formatDate(first.date)}</strong>
            </p>
          ) : (
            <p className="text-navy-900">Still in service at the end of the run</p>
          )}
          <p className="text-steel-500">
            {summary.replacements} replacement(s), {summary.breakdowns} breakdown(s)
          </p>
          {summary.removed_part_categories?.length ? (
            <p className="text-steel-500">Removed parts: {summary.removed_part_categories.join(', ')}</p>
          ) : null}
        </div>
        <div className="text-xs">
          <p className="label-caps">At the end of the run</p>
          <p className="text-navy-900">
            {life ? `${Math.round(life.life_consumed.governing * 100)}% of life used, ageing ${life.ageing_rate.toFixed(2)}x` : '-'}
          </p>
          <p className="text-steel-500">{summary.end_state?.early_warning_headline}</p>
        </div>
        <div style={{ height: 80 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <ReferenceArea y1={0} y2={50} fill="#0f9d58" fillOpacity={0.08} />
              <ReferenceArea y1={50} y2={80} fill="#f4a300" fillOpacity={0.1} />
              <ReferenceArea y1={80} y2={110} fill="#d93025" fillOpacity={0.08} />
              <XAxis dataKey="year" type="number" hide domain={[0, 'dataMax']} />
              <YAxis domain={[0, 110]} hide />
              <Tooltip
                labelFormatter={(v) => `Year ${Number(v).toFixed(1)}`}
                formatter={(v) => [`${v}%`, 'Life used (model)']}
                contentStyle={{ fontSize: '0.7rem' }}
              />
              <Line dataKey="estimated" stroke="#7c3aed" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      <p className="mt-2 text-[0.65rem] text-steel-500">
        {summary.basis} Saved {formatDateTime(scenario.created_at)}
        {scenario.created_by ? ` by ${scenario.created_by}` : ''}.
      </p>
    </article>
  );
}
