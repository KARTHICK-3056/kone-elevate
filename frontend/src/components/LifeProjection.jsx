import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, Gauge, Layers } from 'lucide-react';
import { RecommendationBadge } from './HealthBadge';
import { GRADE_NOT_DETERMINED } from '../utils/constants';
import { cx, formatCurrency, formatDate, formatPercent, humanise } from '../utils/formatters';

/**
 * Passport sections backed by `app.ml.life_model`: what the component is made
 * of, and how its actual usage has moved its life against the design baseline.
 *
 * Both are prototype engineering models, labelled as such. They sit beside the
 * AI assessment as an independent cross-check, never in place of it.
 */

const BAND = {
  green: { fill: '#0f9d58', label: 'Suitable to continue using', chip: 'bg-emerald-100 text-emerald-800' },
  amber: { fill: '#f4a300', label: 'Plan component recovery', chip: 'bg-amber-100 text-amber-900' },
  red: { fill: '#d93025', label: 'Replace band', chip: 'bg-red-100 text-red-800' },
};

const STATUS_STYLE = {
  OK: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  WATCH: 'border-sky-200 bg-sky-50 text-sky-900',
  PLAN: 'border-amber-200 bg-amber-50 text-amber-900',
  ACT: 'border-red-200 bg-red-50 text-red-900',
  OVERDUE: 'border-red-300 bg-red-100 text-red-900',
};

const AVAILABILITY = {
  published_api: { label: 'KONE published API', chip: 'bg-emerald-100 text-emerald-800' },
  not_published: { label: 'Not in KONE API', chip: 'bg-red-100 text-red-800' },
  manual_record: { label: 'Manual record', chip: 'bg-steel-100 text-steel-700' },
};

const years = (value) => (value == null ? '-' : `${Number(value).toFixed(1)} yr`);

/* -------------------------------------------------------------------------- */
/* Material composition                                                       */
/* -------------------------------------------------------------------------- */

/** Every grade of this type priced per year of service, cheapest first. */
function GradeCostComparison({ comparison }) {
  const money = (value) => formatCurrency(value, comparison.currency_symbol, { compact: false });
  return (
    <div className="lg:col-span-2">
      <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-wide text-steel-500">
        Cost comparison by grade
      </p>
      <p className="mb-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
        {comparison.summary}
      </p>
      <div className="overflow-x-auto rounded-lg border border-steel-200">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-steel-50 text-[0.65rem] uppercase tracking-wide text-steel-500">
            <tr>
              <th className="px-3 py-2 font-semibold">Grade</th>
              <th className="px-3 py-2 text-right font-semibold">Part price</th>
              <th className="px-3 py-2 text-right font-semibold">Fitting</th>
              <th className="px-3 py-2 text-right font-semibold">Life at this duty</th>
              <th className="px-3 py-2 text-right font-semibold">Cost per year</th>
              <th className="px-3 py-2 text-right font-semibold">vs best</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-steel-100">
            {comparison.options.map((option) => (
              <tr
                key={option.grade}
                className={cx(option.most_cost_effective && 'bg-emerald-50/60', option.current && 'font-semibold')}
              >
                <td className="px-3 py-2">
                  <span className="text-navy-900">{option.label}</span>
                  <span className="ml-1.5 font-mono text-[0.65rem] text-steel-500">{option.designation}</span>
                  <span className="mt-0.5 flex flex-wrap gap-1">
                    {option.most_cost_effective ? (
                      <span className="badge bg-emerald-100 text-emerald-800">Most cost-effective</span>
                    ) : null}
                    {option.current ? <span className="badge bg-navy-100 text-navy-800">This component</span> : null}
                    {option.lowest_price && !option.most_cost_effective ? (
                      <span className="badge bg-steel-100 text-steel-700">Cheapest to buy</span>
                    ) : null}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono text-steel-700">{money(option.part_price)}</td>
                <td className="px-3 py-2 text-right font-mono text-steel-700">{money(option.fitting_cost)}</td>
                <td className="px-3 py-2 text-right font-mono text-steel-700">{years(option.expected_life_years)}</td>
                <td className="px-3 py-2 text-right font-mono font-semibold text-navy-900">
                  {money(option.cost_per_year)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-steel-600">
                  {option.extra_per_year_vs_best ? `+${money(option.extra_per_year_vs_best)}` : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1.5 text-[0.7rem] text-steel-500">
        Expected life at {comparison.duty_basis} (ageing rate x{Number(comparison.ageing_rate).toFixed(2)}).{' '}
        {comparison.basis}
      </p>
    </div>
  );
}

export function MaterialProfileCard({ profile }) {
  if (!profile) return null;
  const determined = Boolean(profile.grade);
  const assumed = determined && profile.grade_provenance !== 'recorded';
  const factorTone =
    profile.life_factor > 1 ? 'text-emerald-700' : profile.life_factor < 1 ? 'text-red-700' : 'text-navy-900';

  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">Material composition and characteristics</h2>
          <p className="mt-0.5 text-xs text-steel-500">
            Material: {profile.primary_material} - Grade: {profile.grade_label || GRADE_NOT_DETERMINED}
          </p>
        </div>
        <Layers className="h-5 w-5 text-steel-400" aria-hidden="true" />
      </header>

      <div className="card-body grid gap-5 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-wide text-steel-500">
            What it is made of
          </p>
          {!determined ? (
            <p className="rounded-lg border border-dashed border-steel-300 px-3 py-4 text-sm text-steel-600">
              Material grade: <strong>{GRADE_NOT_DETERMINED}</strong>. No grade is catalogued for this
              material, so the composition is shown once a grade is recorded from the nameplate or bill of
              materials.
            </p>
          ) : null}
          {assumed ? (
            <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <span className="badge mr-1.5 bg-amber-100 text-amber-900">Industry standard - assumed</span>
              No grade is recorded, so this is the typical composition of the industry-standard grade for{' '}
              {profile.primary_material}. Record the actual grade to replace it.
            </p>
          ) : null}
          <ul className="space-y-2">
            {(profile.constituents || []).map((item) => (
              <li key={item.name}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-medium text-navy-900">
                    {item.name}
                    {item.separable ? (
                      <span className="ml-1.5 badge bg-blue-50 text-blue-700">recoverable part</span>
                    ) : null}
                  </span>
                  <span className="font-mono text-xs text-steel-600">
                    {formatPercent(item.mass_fraction, 0)}
                  </span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-steel-100">
                  <div
                    className="h-full rounded-full bg-navy-500"
                    style={{ width: `${Math.round(item.mass_fraction * 100)}%` }}
                  />
                </div>
                <p className="mt-0.5 text-[0.7rem] text-steel-500">{item.role}</p>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-4">
          <div className="rounded-lg border border-steel-200 bg-steel-50 p-3">
            <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
              Material life factor
            </p>
            <p className={cx('font-mono text-2xl font-bold', factorTone)}>
              x{Number(profile.life_factor).toFixed(2)}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-steel-600">{profile.life_reasoning}</p>
          </div>

          <dl className="divide-y divide-steel-100 text-sm">
            <div className="flex justify-between gap-4 py-1.5">
              <dt className="text-steel-500">Material</dt>
              <dd className="text-right font-medium text-navy-900">{profile.primary_material}</dd>
            </div>
            <div className="flex justify-between gap-4 py-1.5">
              <dt className="text-steel-500">Material grade</dt>
              <dd className="text-right font-medium text-navy-900">{profile.grade_label || GRADE_NOT_DETERMINED}</dd>
            </div>
            {profile.designation ? (
              <div className="flex justify-between gap-4 py-1.5">
                <dt className="text-steel-500">Grade designation</dt>
                <dd className="text-right font-mono font-semibold text-navy-900">{profile.designation}</dd>
              </div>
            ) : null}
            {profile.grading_system ? (
              <div className="flex justify-between gap-4 py-1.5">
                <dt className="text-steel-500">Grading standard</dt>
                <dd className="text-right font-medium text-navy-900">{profile.grading_system}</dd>
              </div>
            ) : null}
            {profile.equivalent ? (
              <div className="flex justify-between gap-4 py-1.5">
                <dt className="text-steel-500">Equivalent</dt>
                <dd className="text-right font-mono text-navy-900">{profile.equivalent}</dd>
              </div>
            ) : null}
            {(profile.properties || []).map((item) => (
              <div key={item.property} className="flex justify-between gap-4 py-1.5">
                <dt className="text-steel-500">{item.property}</dt>
                <dd className="text-right font-medium text-navy-900">{item.value}</dd>
              </div>
            ))}
            {profile.material_recoverability ? (
              <div className="flex justify-between gap-4 py-1.5">
                <dt className="text-steel-500">Material recoverability</dt>
                <dd className="text-right font-medium text-navy-900">{profile.material_recoverability}</dd>
              </div>
            ) : null}
          </dl>

          <div>
            <p className="mb-1 text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
              {determined && !assumed ? 'Same component, other grades' : 'Grades this component could be'}
            </p>
            <ul className="space-y-1 text-xs">
              {profile.alternatives.map((alt) => (
                <li
                  key={alt.grade}
                  className={cx(
                    'flex justify-between gap-3 rounded px-2 py-1',
                    alt.grade === profile.grade ? 'bg-navy-50 font-semibold text-navy-900' : 'text-steel-600',
                  )}
                >
                  <span>
                    {alt.label}
                    {alt.designation ? (
                      <span className="ml-1.5 font-mono text-[0.65rem] text-steel-500">{alt.designation}</span>
                    ) : null}
                  </span>
                  <span className="font-mono">x{Number(alt.life_factor).toFixed(2)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {profile.cost_comparison ? <GradeCostComparison comparison={profile.cost_comparison} /> : null}

        {profile.specifications?.length ? (
          <div className="lg:col-span-2">
            <p className="mb-2 text-[0.7rem] font-semibold uppercase tracking-wide text-steel-500">
              Material specification by part
            </p>
            <div className="overflow-x-auto rounded-lg border border-steel-200">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-steel-50 text-[0.65rem] uppercase tracking-wide text-steel-500">
                  <tr>
                    <th className="px-3 py-2 font-semibold">Part</th>
                    <th className="px-3 py-2 font-semibold">Grade</th>
                    <th className="px-3 py-2 font-semibold">Standard</th>
                    <th className="px-3 py-2 font-semibold">Equivalent</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-steel-100">
                  {profile.specifications.map((row) => (
                    <tr key={row.part}>
                      <td className="px-3 py-2 font-medium text-navy-900">{row.part}</td>
                      <td className="px-3 py-2 font-mono font-semibold text-navy-900">{row.grade}</td>
                      <td className="px-3 py-2 text-steel-600">{row.standard}</td>
                      <td className="px-3 py-2 font-mono text-steel-600">{row.equivalent || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-1.5 text-[0.7rem] text-steel-500">{profile.specification_notice}</p>
          </div>
        ) : null}
      </div>

      <p
        className={cx(
          'border-t border-steel-100 px-5 py-3 text-[0.7rem] leading-relaxed',
          profile.grade_provenance === 'recorded' ? 'text-steel-500' : 'bg-amber-50/60 text-amber-900',
        )}
      >
        {profile.grade_note} {profile.basis}
      </p>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Pre-emptive life projection                                                */
/* -------------------------------------------------------------------------- */
export function LifeProjectionCard({ life }) {
  if (!life) return null;
  if (!life.supported || !life.available) {
    return (
      <section className="card">
        <header className="card-header">
          <h2 className="card-title">Pre-emptive life projection</h2>
        </header>
        <p className="card-body text-sm text-steel-500">{life.reason}</p>
      </section>
    );
  }

  const { projection, life_consumed: consumed, implication, status } = life;
  const band = BAND[life.band];
  // Positive: worn more than its actual age implies (used harder than design).
  const ageGap = life.effective_age_years - life.calendar_age_years;
  const lifeChange = projection.life_change_years;
  // From the life change, not today's rate: past wear (or a governing
  // inspection) can move total life the other way from today's usage.
  const faster = lifeChange < -0.1;
  const slower = lifeChange > 0.1;

  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">Pre-emptive life projection</h2>
          <p className="mt-0.5 text-xs text-steel-500">
            Expected life vs. how it has actually been used - wears by {life.mechanism.toLowerCase()}
          </p>
        </div>
        <Gauge className="h-5 w-5 text-steel-400" aria-hidden="true" />
      </header>

      <div className="card-body space-y-5">
        <div className={cx('rounded-lg border px-4 py-3', STATUS_STYLE[status.level])}>
          <p className="text-sm font-bold">
            {status.level} - {status.message}
          </p>
          <p className="mt-1 text-xs">
            Wearing at <strong>{life.ageing_rate.toFixed(2)}x</strong> the design rate today
            {life.historical_ageing_rate != null
              ? ` (${Number(life.historical_ageing_rate).toFixed(2)}x on average since installation${
                  life.readings_in_history ? `, from ${life.readings_in_history} dated readings` : ''
                })`
              : ''}
            .
            {faster
              ? ` The way it is used is shortening its life by ${Math.abs(lifeChange).toFixed(1)} years.`
              : slower
                ? ` Lighter-than-design use is extending its life by ${lifeChange.toFixed(1)} years.`
                : ' It is being used close to its design duty.'}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <Stat
            label="Expected life"
            value={years(life.design_life_years)}
            sub="How long this type and grade should last at normal (design) use"
          />
          <Stat
            label="Actual age"
            value={years(life.calendar_age_years)}
            sub="Time since it was installed"
          />
          <Stat
            label="Usage-based age"
            value={years(life.effective_age_years)}
            tone={ageGap > 0.1 ? 'text-red-700' : ageGap < -0.1 ? 'text-emerald-700' : undefined}
            sub={
              Math.abs(ageGap) < 0.1
                ? 'How old it is in wear terms - same as its actual age'
                : `How old it is in wear terms - ${Math.abs(ageGap).toFixed(1)} yr ${
                    ageGap > 0 ? 'older' : 'younger'
                  } than its actual age`
            }
          />
          <Stat
            label="Life used"
            value={formatPercent(consumed.governing, 0)}
            sub="Usage-based age as a share of the expected life"
            chip={<span className={cx('badge', band.chip)}>{band.label}</span>}
          />
          <Stat
            label="Remaining life"
            value={years(projection.years_to_end_of_life)}
            sub={`If today's usage continues - until ${formatDate(projection.end_of_life_date)}`}
          />
          <Stat
            label="Projected total life"
            value={years(projection.projected_total_life_years)}
            tone={lifeChange < -0.1 ? 'text-red-700' : lifeChange > 0.1 ? 'text-emerald-700' : undefined}
            sub={
              Math.abs(lifeChange) < 0.1
                ? 'Actual age + remaining life - as expected'
                : `Actual age + remaining life - ${Math.abs(lifeChange).toFixed(1)} yr ${
                    lifeChange < 0 ? 'shorter' : 'longer'
                  } than expected`
            }
          />
        </div>

        <LifeChart life={life} />

        <div className="grid gap-3 sm:grid-cols-3">
          <Milestone
            color={BAND.amber.fill}
            label="Half of expected life used (50%)"
            years={projection.years_to_half_life}
            date={projection.half_life_date}
          />
          <Milestone
            color={BAND.red.fill}
            label="Enters replace band (80% used)"
            years={projection.years_to_replace_band}
            date={projection.replace_band_date}
          />
          <Milestone
            color="#0f1c33"
            label="End of expected life (100% used)"
            years={projection.years_to_end_of_life}
            date={projection.end_of_life_date}
          />
        </div>

        {consumed.divergence_note ? (
          <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              <strong>Usage model {formatPercent(consumed.usage_model, 0)} vs. inspection{' '}
                {formatPercent(consumed.inspection, 0)}.</strong>{' '}
              {consumed.divergence_note}
            </span>
          </div>
        ) : null}

        <ImplicationPanel implication={implication} />
        <FactorTable life={life} />

        <div>
          <p className="mb-1 text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
            What an inspector measures (no telemetry replaces these)
          </p>
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-steel-600">
            {life.discard_criteria.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>

        <p className="rounded-lg bg-steel-100 px-3 py-2 text-[0.7rem] leading-relaxed text-steel-600">
          Expected life = {years(life.base_design_life_years)} design life for a {life.component_type.toLowerCase()} x
          material factor {Number(life.material_factor).toFixed(2)} for its grade ={' '}
          {years(life.design_life_years)}. Usage-based age = life used x expected life.{' '}
          {projection.assumption} {life.basis}
        </p>
      </div>
    </section>
  );
}

function Stat({ label, value, sub, tone, chip }) {
  return (
    <div className="rounded-lg border border-steel-200 p-3">
      <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">{label}</p>
      <p className={cx('font-mono text-xl font-bold text-navy-900', tone)}>{value}</p>
      {sub ? <p className="text-[0.7rem] text-steel-500">{sub}</p> : null}
      {chip ? <div className="mt-1">{chip}</div> : null}
    </div>
  );
}

function Milestone({ color, label, years: value, date }) {
  const reached = value === 0;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-steel-200 p-3">
      <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
      <div>
        <p className="text-xs font-semibold text-navy-900">{label}</p>
        <p className="text-xs text-steel-600">
          {reached ? 'Already reached' : `in ${Number(value).toFixed(1)} yr - ${formatDate(date)}`}
        </p>
      </div>
    </div>
  );
}

function LifeChart({ life }) {
  const data = life.trajectory;
  const todayYear = data.find((p) => p.actual != null && p.projected != null)?.year;
  const maxY = Math.max(110, ...data.map((p) => Math.max(p.design, p.actual ?? 0, p.projected ?? 0)));
  const top = Math.min(160, Math.ceil(maxY / 10) * 10);
  const first = Math.ceil(data[0].year);
  const last = Math.floor(data[data.length - 1].year);
  const step = [1, 2, 5, 10].find((n) => (last - first) / n <= 8) ?? 20;
  const ticks = [];
  for (let y = Math.ceil(first / step) * step; y <= last; y += step) ticks.push(y);
  const tooltip = (value, name) => [value == null ? '-' : `${Number(value).toFixed(0)}%`, name];

  return (
    <div>
      <div style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 10, right: 16, bottom: 4, left: 0 }}>
            <ReferenceArea y1={0} y2={50} fill={BAND.green.fill} fillOpacity={0.1} ifOverflow="hidden" />
            <ReferenceArea y1={50} y2={80} fill={BAND.amber.fill} fillOpacity={0.12} ifOverflow="hidden" />
            <ReferenceArea y1={80} y2={top} fill={BAND.red.fill} fillOpacity={0.1} ifOverflow="hidden" />
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis
              dataKey="year"
              type="number"
              domain={['dataMin', 'dataMax']}
              ticks={ticks}
              tickFormatter={(v) => Math.round(v)}
              stroke="#8593aa"
              fontSize={11}
            />
            <YAxis
              domain={[0, top]}
              tickFormatter={(v) => `${v}%`}
              label={{ value: 'Life used', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#5b6b86' }}
              stroke="#8593aa"
              fontSize={11}
              width={44}
            />
            <Tooltip
              formatter={tooltip}
              labelFormatter={(v) => `Year ${Number(v).toFixed(1)}`}
              contentStyle={{ borderRadius: '0.5rem', border: '1px solid #d5dae3', fontSize: '0.8rem' }}
            />
            <Legend wrapperStyle={{ fontSize: '0.75rem' }} />
            <ReferenceLine y={100} stroke="#0f1c33" strokeDasharray="4 4" label={{ value: 'End of expected life', position: 'insideTopLeft', fontSize: 10, fill: '#0f1c33' }} />
            {todayYear != null ? (
              <ReferenceLine x={todayYear} stroke="#0aa2c0" label={{ value: 'Today', position: 'top', fontSize: 10, fill: '#077f97' }} />
            ) : null}
            <Line
              type="linear"
              dataKey="design"
              name="Wear at normal (design) use"
              stroke="#8593aa"
              strokeDasharray="6 4"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="actual"
              name="Actual wear so far"
              stroke="#0f1c33"
              strokeWidth={2.5}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="projected"
              name="Projected wear if today's usage continues"
              stroke="#d93025"
              strokeDasharray="2 3"
              strokeWidth={2.5}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-[0.7rem] text-steel-600">
        {Object.entries(BAND).map(([key, value]) => (
          <span key={key} className="flex items-center gap-1.5">
            <span className="h-2.5 w-4 rounded-sm" style={{ background: value.fill, opacity: 0.45 }} />
            {value.label}
            {key === 'green' ? ' (<50%)' : key === 'amber' ? ' (50-80%)' : ' (>80%)'}
          </span>
        ))}
      </div>
    </div>
  );
}

function ImplicationPanel({ implication }) {
  return (
    <div className="rounded-lg border border-steel-200 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-steel-500">
          Life position suggests
        </span>
        <RecommendationBadge recommendation={implication.recommendation} size="sm" />
        {implication.ai_recommendation ? (
          <span
            className={cx(
              'badge',
              implication.agrees_with_ai ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-900',
            )}
          >
            {implication.agrees_with_ai
              ? 'Agrees with AI assessment'
              : `AI assessment says ${humanise(implication.ai_recommendation)}`}
          </span>
        ) : null}
      </div>
      <p className="mt-1.5 text-xs text-steel-600">{implication.reason}</p>
      {implication.safety_gate ? (
        <p className="mt-1 text-xs font-semibold text-red-700">
          Safety-critical: mandatory human inspection applies whatever this projection says.
        </p>
      ) : null}
    </div>
  );
}

function FactorTable({ life }) {
  return (
    <div>
      <p className="mb-1 text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
        Why it is ageing at this rate - and where each input comes from
      </p>
      <div className="overflow-x-auto rounded-lg border border-steel-200">
        <table className="w-full min-w-[640px] text-left text-xs">
          <thead className="bg-steel-50 text-[0.65rem] uppercase tracking-wide text-steel-500">
            <tr>
              <th className="px-3 py-2">Driver</th>
              <th className="px-3 py-2">Effect now (history)</th>
              <th className="px-3 py-2">Observed vs. design</th>
              <th className="px-3 py-2">Data source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-steel-100">
            {life.factors.map((factor) => {
              const m = factor.multiplier;
              const tone = m > 1.02 ? 'text-red-700' : m < 0.98 ? 'text-emerald-700' : 'text-steel-600';
              return (
                <tr key={factor.key} className="align-top">
                  <td className="px-3 py-2">
                    <p className="font-semibold text-navy-900">{factor.label}</p>
                    <p className="mt-0.5 text-[0.7rem] text-steel-500">{factor.explanation}</p>
                  </td>
                  <td className={cx('px-3 py-2 font-mono font-bold', tone)}>
                    x{m.toFixed(2)}
                    {factor.history_multiplier != null && factor.history_multiplier !== m ? (
                      <span className="block text-[0.7rem] font-normal text-steel-500">
                        history x{Number(factor.history_multiplier).toFixed(2)}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-steel-600">
                    <p>{factor.observed ?? 'not recorded'}</p>
                    <p className="text-[0.7rem] text-steel-400">{factor.reference}</p>
                  </td>
                  <td className="px-3 py-2">
                    {factor.sources.map((source) => (
                      <div key={source.field} className="mb-1">
                        <span className={cx('badge', AVAILABILITY[source.availability]?.chip)}>
                          {AVAILABILITY[source.availability]?.label}
                        </span>
                        <p className="mt-0.5 text-[0.7rem] text-steel-500">{source.kone_source}</p>
                      </div>
                    ))}
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
