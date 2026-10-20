import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  FlaskConical,
  Info,
  Pause,
  Play,
  RotateCcw,
  Save,
  SkipForward,
  Users,
} from 'lucide-react';
import ElevatorScene from '../components/ElevatorScene';
import { EarlyWarningPanel } from '../components/EarlyWarning';
import { RecommendationBadge } from '../components/HealthBadge';
import ErrorMessage from '../components/ErrorMessage';
import Loading from '../components/Loading';
import { SPEEDS, useSimulation } from '../hooks/useSimulation';
import { componentsApi } from '../api/client';
import { cx, formatDate, formatNumber, humanise } from '../utils/formatters';

/**
 * Interactive lift simulation.
 *
 * The user sets one number - the average load per trip. The backend derives
 * all 13 model parameters for motor, rope, sheave and governor from it, runs the
 * life model, early-warning forecast and AI classifier on them, and drives
 * maintenance from the predictions. The 3D model is a visual of the same
 * results.
 */

const COMPONENTS = ['Motor', 'Steel Rope', 'Sheave', 'Governor'];
const COMPONENT_COLOR = { Motor: '#1a73e8', 'Steel Rope': '#7c3aed', Sheave: '#0aa2c0', Governor: '#e8710a' };
const BAND = {
  green: { label: 'Suitable to continue using', chip: 'bg-emerald-100 text-emerald-800', dot: 'bg-emerald-500' },
  amber: { label: 'Plan component recovery', chip: 'bg-amber-100 text-amber-900', dot: 'bg-amber-500' },
  red: { label: 'Replace band', chip: 'bg-red-100 text-red-800', dot: 'bg-red-500' },
};
const SOURCE = {
  kone_api: { label: 'KONE API', chip: 'bg-sky-100 text-sky-800' },
  input: { label: 'Your input', chip: 'bg-navy-100 text-navy-800' },
  standard: { label: 'Standard', chip: 'bg-emerald-100 text-emerald-800' },
  simulated: { label: 'Simulated', chip: 'bg-violet-100 text-violet-800' },
  physics: { label: 'Calculated (physics)', chip: 'bg-violet-50 text-violet-700' },
  assumption: { label: 'Assumption', chip: 'bg-steel-100 text-steel-700' },
};
const EVENT_STYLE = {
  warning: 'border-l-amber-500',
  replace_proactive: 'border-l-emerald-500',
  breakdown: 'border-l-red-600',
  callout: 'border-l-red-300',
  load: 'border-l-steel-300',
};
const PARAMETER_LABELS = {
  component_type: 'Component type',
  material: 'Material',
  component_age: 'Age (years)',
  operating_hours: 'Operating hours',
  load_cycles: 'Load cycles',
  average_load: 'Equivalent load (kg, component scale)',
  vibration: 'Vibration (mm/s)',
  temperature: 'Temperature (C)',
  service_count: 'Service visits',
  repair_count: 'Repairs',
  failure_history: 'Failures',
  inspection_score: 'Inspection score',
  days_since_last_service: 'Days since service',
};
const PRESETS = [
  { label: 'Light', kg: 150 },
  { label: 'Typical', kg: 460 },
  { label: 'Heavy', kg: 800 },
  { label: 'Full', kg: 1000 },
];

const pct = (value) => (value == null ? '-' : `${Math.round(value * 100)}%`);

export default function Simulation() {
  const [searchParams, setSearchParams] = useSearchParams();
  const sim = useSimulation(460, searchParams.get('component'));
  const { reference, results } = sim;
  const [selected, setSelected] = useState('Motor');
  const focusType = results?.focus?.component_type;
  useEffect(() => {
    if (focusType) setSelected(focusType);
  }, [focusType]);
  const lift = reference?.reference?.lift;
  const maxLoad = lift?.max_load_kg?.value ?? 1100;
  const referenceLoad = reference?.reference?.traffic?.reference_load_kg?.value;
  // A backend still running older code simulates a different set of parts;
  // say so instead of crashing on the part it did not send.
  const missingParts = results ? COMPONENTS.filter((c) => !results.components?.[c]) : [];

  const visual = useMemo(() => {
    if (!results || COMPONENTS.some((c) => !results.components?.[c])) {
      return { floors: lift?.floors?.value, floorHeight: lift?.floor_height_m?.value };
    }
    const comps = results.components;
    const bands = Object.fromEntries(COMPONENTS.map((c) => [c, comps[c]?.life?.band]));
    const vibrationRatio = Math.max(
      ...COMPONENTS.map((c) => (comps[c].truth.vibration || 0) / comps[c].truth.vibration_limit),
    );
    const motor = comps.Motor.truth;
    return {
      floors: lift?.floors?.value,
      floorHeight: lift?.floor_height_m?.value,
      loadKg: sim.load,
      bands,
      vibrationRatio,
      motorHeat: (motor.temperature - 60) / (motor.temperature_limit + 10 - 60),
    };
  }, [results, lift, sim.load]);

  if (!results && !sim.error) return <Loading label="Building the simulated lift..." />;
  if (missingParts.length) {
    return (
      <ErrorMessage
        title="The simulation server is out of date"
        error={{
          message: `The backend simulated ${Object.keys(results.components || {}).join(', ')}, but this page expects ${COMPONENTS.join(', ')}. Restart the backend so it runs the current code, then try again.`,
        }}
        onRetry={sim.reset}
      />
    );
  }
  // A shorter 3D view on phones leaves room for the controls below it.
  const sceneHeight = typeof window !== 'undefined' && window.innerWidth < 640 ? 340 : 520;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-navy-900">Lift simulation</h1>
          <p className="mt-1 max-w-3xl text-sm text-steel-500">
            Set the average load the car carries. The simulation derives all 13 model parameters for
            the motor, steel ropes, sheave and overspeed governor, and every life-span figure on this page is
            calculated from them.
          </p>
        </div>
        {results ? (
          <div className="rounded-lg border border-steel-200 bg-white px-4 py-2 text-right">
            <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">Simulated date</p>
            <p className="font-mono text-lg font-bold text-navy-900">{formatDate(results.date)}</p>
            <p className="text-xs text-steel-500">{results.years.toFixed(1)} years in service</p>
          </div>
        ) : null}
      </header>

      {reference ? <DataNotice reference={reference.reference} /> : null}
      <StartPanel
        sim={sim}
        onStartFrom={(id) => {
          setSearchParams({ component: id });
          sim.startFrom(id);
        }}
        onNewLift={() => {
          setSearchParams({});
          sim.reset();
        }}
      />
      {results?.focus ? <FocusBanner focus={results.focus} sim={sim} /> : null}
      {sim.error ? <ErrorMessage error={sim.error} onRetry={sim.reset} title="Simulation error" /> : null}

      {results ? (
        <>
          <div id="sim-model" className="grid gap-5 lg:grid-cols-5">
            <section className="card lg:col-span-3">
              <header className="card-header">
                <div>
                  <h2 className="card-title">3D model</h2>
                  <p className="mt-0.5 text-xs text-steel-500">
                    Drag to orbit, scroll to zoom. Colours show each part&apos;s life band; the motor
                    glows with heat; the machine shakes with vibration.
                  </p>
                </div>
              </header>
              <div className="p-3">
                <ElevatorScene visual={visual} height={sceneHeight} />
              </div>
            </section>

            <div className="space-y-5 lg:col-span-2">
              <Controls sim={sim} maxLoad={maxLoad} referenceLoad={referenceLoad} />
              <Kpis kpis={results.kpis} />
            </div>
          </div>

          <div id="sim-parts" className="grid scroll-mt-32 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {COMPONENTS.map((c) => (
              <ComponentTile
                key={c}
                name={c}
                data={results.components[c]}
                focus={results.focus}
                active={selected === c}
                onSelect={() => setSelected(c)}
              />
            ))}
          </div>

          <WearChart series={sim.series} selected={selected} onSelect={setSelected} />

          <ComponentDetail name={selected} data={results.components[selected]} />

          <div id="sim-parameters" className="scroll-mt-32">
            <ParameterTable results={results} basis={reference?.parameter_basis} referenceLoad={referenceLoad} />
          </div>

          <div id="sim-log" className="grid scroll-mt-32 gap-5 lg:grid-cols-2">
            <EventLog events={sim.events} />
            {reference ? <ReferenceCard reference={reference.reference} /> : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

function DataNotice({ reference }) {
  return (
    <div className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
      <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <p>
        <strong>Where the numbers come from.</strong> {reference.notice} KONE API source right now:{' '}
        <strong>{reference.api_values_are_real ? 'live' : 'recorded example responses'}</strong>.
      </p>
    </div>
  );
}

function Controls({ sim, maxLoad, referenceLoad }) {
  const persons = sim.load / 75;
  return (
    <section className="card">
      <header className="card-header">
        <h2 className="card-title">Your input: average load per trip</h2>
      </header>
      <div className="card-body space-y-4">
        <div>
          <div className="flex items-end justify-between gap-3">
            <label htmlFor="sim-load" className="font-mono text-3xl font-extrabold text-navy-900">
              {Math.round(sim.load)} <span className="text-base font-semibold text-steel-500">kg</span>
            </label>
            <span className="flex items-center gap-1 text-sm text-steel-600">
              <Users className="h-4 w-4" aria-hidden="true" />~{persons.toFixed(1)} persons
            </span>
          </div>
          <input
            id="sim-load"
            type="range"
            min={0}
            max={maxLoad}
            step={10}
            value={sim.load}
            onChange={(event) => sim.setLoad(Number(event.target.value))}
            className="mt-2 w-full accent-accent"
            aria-label="Average load per trip in kilograms"
          />
          <div className="flex justify-between text-[0.65rem] text-steel-400">
            <span>0 kg</span>
            <span>Rated 1000 kg</span>
            <span>{maxLoad} kg (overload limit)</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                className={cx('btn-ghost btn-sm', sim.load === preset.kg && 'bg-navy-50 text-navy-900')}
                onClick={() => sim.setLoad(preset.kg)}
              >
                {preset.label} {preset.kg}
              </button>
            ))}
            <input
              type="number"
              min={0}
              max={maxLoad}
              value={sim.load}
              onChange={(event) => sim.setLoad(Math.max(0, Math.min(maxLoad, Number(event.target.value) || 0)))}
              className="input w-24 py-1 text-sm"
              aria-label="Load in kilograms"
            />
          </div>
          {referenceLoad ? (
            <p className="mt-1 text-[0.7rem] text-steel-500">
              Design life is referenced to {referenceLoad} kg (KONE movement feed loadPercentage). Changes
              apply from the next simulated month.
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-steel-100 pt-4">
          <button
            type="button"
            className="btn-accent"
            onClick={() => sim.setRunning(!sim.running)}
          >
            {sim.running ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {sim.running ? 'Pause' : 'Run'}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => sim.step(sim.speed)}
            disabled={sim.running || sim.busy}
          >
            <SkipForward className="h-4 w-4" />
            Step
          </button>
          <button type="button" className="btn-ghost" onClick={sim.reset} disabled={sim.busy && !sim.running}>
            <RotateCcw className="h-4 w-4" />
            New lift
          </button>
          <select
            className="select w-auto py-1.5 text-sm"
            value={sim.speed}
            onChange={(event) => sim.setSpeed(Number(event.target.value))}
            aria-label="Simulation speed"
          >
            {SPEEDS.map((speed) => (
              <option key={speed.months} value={speed.months}>
                {speed.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </section>
  );
}

function Kpis({ kpis }) {
  const items = [
    { label: 'Replaced before failure', value: kpis.proactive_replacements, tone: 'text-emerald-700' },
    { label: 'Breakdowns', value: kpis.breakdowns, tone: kpis.breakdowns ? 'text-red-700' : 'text-navy-900' },
    { label: 'Removed parts to Component Recovery', value: kpis.to_component_recovery },
    { label: 'To Material Recovery', value: kpis.to_material_recovery },
    { label: 'To Dispose', value: kpis.to_dispose },
    { label: 'Callouts', value: kpis.callouts },
    { label: 'Early warnings', value: kpis.warnings_raised },
    {
      label: 'Avg warning lead',
      value: kpis.average_warning_lead_months != null ? `${kpis.average_warning_lead_months} mo` : '-',
    },
  ];
  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">Did the pre-analysis work?</h2>
          <p className="mt-0.5 text-xs text-steel-500">
            Maintenance here is driven by the predictions - these count the outcome.
          </p>
        </div>
      </header>
      <div className="card-body grid grid-cols-3 gap-3">
        {items.map((item) => (
          <div key={item.label}>
            <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">{item.label}</p>
            <p className={cx('font-mono text-xl font-bold', item.tone || 'text-navy-900')}>{item.value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function ComponentTile({ name, data, focus, active, onSelect }) {
  const life = data.life;
  const band = BAND[life?.band] || BAND.green;
  const warning = data.early_warning;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cx(
        'card p-4 text-left transition hover:shadow-elevated',
        active && 'ring-2 ring-accent',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-bold text-navy-900">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: COMPONENT_COLOR[name] }} />
          {name}
        </p>
        <span className={cx('badge', band.chip)}>{band.label}</span>
      </div>
      {focus ? (
        <p className="mt-1">
          {focus.component_type === name ? (
            <span className="badge bg-navy-900 text-white">Real record: {focus.component_id}</span>
          ) : (
            <span className="badge bg-steel-100 text-steel-600">Simulated companion</span>
          )}
        </p>
      ) : null}
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div>
          <p className="text-steel-500">Life used (model)</p>
          <p className="font-mono text-lg font-bold text-navy-900">{pct(life?.life_consumed?.governing)}</p>
        </div>
        <div>
          <p className="text-steel-500">True wear (sim)</p>
          <p className="font-mono text-lg font-bold text-steel-600">{pct(data.truth.wear)}</p>
        </div>
        <div>
          <p className="text-steel-500">Ageing rate</p>
          <p className="font-mono font-semibold">{life?.ageing_rate?.toFixed(2)}x</p>
        </div>
        <div>
          <p className="text-steel-500">Life remaining</p>
          <p className="font-mono font-semibold">{life?.projection?.years_to_end_of_life?.toFixed(1)} yr</p>
        </div>
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        <span className="text-steel-500">AI:</span>
        {data.ai ? <RecommendationBadge recommendation={data.ai.recommendation} size="sm" /> : '-'}
        <span className="text-steel-400">Part #{data.truth.life_number}</span>
      </div>
      {warning?.issues?.length ? (
        <p className="mt-2 line-clamp-2 text-[0.7rem] text-amber-800">{warning.headline}</p>
      ) : (
        <p className="mt-2 text-[0.7rem] text-emerald-700">No issue predicted within 3 years.</p>
      )}
    </button>
  );
}

function WearChart({ series, selected, onSelect }) {
  const data = series.map((point) => ({
    year: point.month / 12,
    estimated: Math.round(point[selected].estimated * 1000) / 10,
    truth: Math.round(point[selected].true_wear * 1000) / 10,
    load: point.load_kg,
  }));
  return (
    <section className="card">
      <header className="card-header flex-wrap">
        <div>
          <h2 className="card-title">Life used over simulated time</h2>
          <p className="mt-0.5 text-xs text-steel-500">
            Solid: what the models estimate from observed data. Dashed: the simulation&apos;s hidden true
            wear. Drops are replacements.
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          {COMPONENTS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => onSelect(c)}
              className={cx('btn-ghost btn-sm', selected === c && 'bg-navy-50 text-navy-900')}
            >
              {c}
            </button>
          ))}
        </div>
      </header>
      <div className="p-4" style={{ height: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <ReferenceArea y1={0} y2={50} fill="#0f9d58" fillOpacity={0.08} />
            <ReferenceArea y1={50} y2={80} fill="#f4a300" fillOpacity={0.1} />
            <ReferenceArea y1={80} y2={120} fill="#d93025" fillOpacity={0.08} />
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis
              dataKey="year"
              type="number"
              domain={[0, 'dataMax']}
              tickFormatter={(v) => `${Math.round(v)}y`}
              stroke="#8593aa"
              fontSize={11}
            />
            <YAxis domain={[0, 110]} tickFormatter={(v) => `${v}%`} stroke="#8593aa" fontSize={11} width={44} />
            <ReferenceLine y={100} stroke="#0f1c33" strokeDasharray="4 4" />
            <Tooltip
              labelFormatter={(v) => `Year ${Number(v).toFixed(1)}`}
              formatter={(value, name) => [`${value}%`, name]}
              contentStyle={{ borderRadius: '0.5rem', fontSize: '0.8rem' }}
            />
            <Legend wrapperStyle={{ fontSize: '0.75rem' }} />
            <Line
              dataKey="estimated"
              name={`${selected} - model estimate`}
              stroke={COMPONENT_COLOR[selected]}
              strokeWidth={2.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              dataKey="truth"
              name={`${selected} - simulated true wear`}
              stroke="#0f1c33"
              strokeDasharray="5 4"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function ComponentDetail({ name, data }) {
  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">{name}: why it is ageing, and what is coming</h2>
          <p className="mt-0.5 text-xs text-steel-500">{data.life?.mechanism}</p>
        </div>
        {data.safety_critical ? <span className="badge bg-red-50 text-red-700">Safety-critical</span> : null}
      </header>
      <div className="card-body space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-steel-200 p-3 text-xs">
            <p className="label-caps">Load on this part</p>
            <p className="font-mono text-lg font-bold text-navy-900">
              {data.truth.load_stress_ratio.toFixed(2)}x reference
            </p>
            <p className="text-steel-500">Miner-equivalent stress from your load</p>
          </div>
          <div className="rounded-lg border border-steel-200 p-3 text-xs">
            <p className="label-caps">Live readings (sim)</p>
            <p className="font-mono text-sm text-navy-900">
              {data.truth.vibration?.toFixed(2)} / {data.truth.vibration_limit} mm/s
            </p>
            <p className="font-mono text-sm text-navy-900">
              {data.truth.temperature?.toFixed(1)} / {data.truth.temperature_limit} C
            </p>
          </div>
          <div className="rounded-lg border border-steel-200 p-3 text-xs">
            <p className="label-caps">AI classifier (last service visit)</p>
            {data.ai ? (
              <>
                <RecommendationBadge recommendation={data.ai.recommendation} size="sm" />
                <p className="mt-1 text-steel-500">
                  {Math.round(data.ai.confidence * 100)}% on {humanise(data.ai.underlying)}
                </p>
              </>
            ) : (
              <p className="text-steel-500">No model loaded.</p>
            )}
          </div>
        </div>

        <div>
          <p className="label-caps">Life model factors (from the 13 parameters)</p>
          <div className="flex flex-wrap gap-1.5">
            {data.factors.map((factor) => (
              <span
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
              </span>
            ))}
          </div>
        </div>

        {data.early_warning?.supported ? (
          <div>
            <p className="label-caps">Pre-emptive issue forecast</p>
            <p className="mb-2 text-sm font-semibold text-navy-900">{data.early_warning.headline}</p>
            <EarlyWarningPanel forecast={data.early_warning} />
          </div>
        ) : null}
      </div>
    </section>
  );
}

function formatParameter(key, value) {
  if (typeof value === 'number') {
    if (['operating_hours', 'load_cycles'].includes(key)) return formatNumber(Math.round(value));
    return Number.isInteger(value) ? String(value) : value.toFixed(key === 'component_age' ? 2 : 1);
  }
  return value ?? '-';
}

function ParameterTable({ results, basis, referenceLoad }) {
  const keys = Object.keys(PARAMETER_LABELS);
  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">The 13 model parameters - KONE API first</h2>
          <p className="mt-0.5 text-xs text-steel-500">
            Exactly what the life model, early-warning forecast and AI classifier receive. Every value
            the KONE API publishes starts from the reference lift&apos;s KONE record; only what KONE does not
            publish (vibration, temperature, component age) is simulated.
          </p>
        </div>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-xs">
          <thead className="bg-steel-50 text-[0.65rem] uppercase tracking-wide text-steel-500">
            <tr>
              <th className="px-3 py-2">Parameter</th>
              {COMPONENTS.map((c) => (
                <th key={c} className="px-3 py-2 text-right">
                  {c}
                </th>
              ))}
              <th className="px-3 py-2">How it is derived</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-steel-100">
            {keys.map((key) => {
              const how = basis?.[key];
              // The load row is KONE's value until the user changes it.
              const changedLoad =
                how?.input_source && referenceLoad != null && Math.abs(results.load_kg - referenceLoad) > 1e-6;
              const source = SOURCE[changedLoad ? how.input_source : how?.source];
              return (
                <tr key={key} className="align-top">
                  <td className="px-3 py-2 font-semibold text-navy-900">{PARAMETER_LABELS[key]}</td>
                  {COMPONENTS.map((c) => (
                    <td key={c} className="px-3 py-2 text-right font-mono text-steel-700">
                      {formatParameter(key, results.components[c].parameters[key])}
                    </td>
                  ))}
                  <td className="px-3 py-2 text-steel-600">
                    {source ? <span className={cx('badge mr-1', source.chip)}>{source.label}</span> : null}
                    {how?.how}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EventLog({ events }) {
  const shown = [...events].reverse().slice(0, 60);
  return (
    <section className="card">
      <header className="card-header">
        <h2 className="card-title">Simulation log</h2>
      </header>
      <ul className="max-h-96 divide-y divide-steel-100 overflow-y-auto">
        {shown.length ? (
          shown.map((event, index) => (
            <li
              key={`${event.month}-${event.kind}-${event.component}-${index}`}
              className={cx('border-l-4 px-4 py-2 text-xs', EVENT_STYLE[event.kind] || 'border-l-steel-200')}
            >
              <p className="text-[0.65rem] text-steel-400">
                {formatDate(event.date)} - year {(event.month / 12).toFixed(1)}
                {event.component ? ` - ${event.component}` : ''}
              </p>
              <p className="text-steel-700">{event.message}</p>
            </li>
          ))
        ) : (
          <li className="px-4 py-6 text-center text-sm text-steel-400">Press Run to start the lift.</li>
        )}
      </ul>
    </section>
  );
}

function ReferenceCard({ reference }) {
  const record = reference.kone_record;
  const koneStart = record
    ? Object.fromEntries(
        Object.entries(record.start)
          .filter(([, value]) => value !== null && value !== undefined)
          .map(([key, value]) => [
            key,
            { value, unit: '', source: 'kone_api', basis: record.start_notes?.[key] || '' },
          ]),
      )
    : null;
  const groups = [
    ...(koneStart ? [[`KONE record at month 0 (${record.orders} service orders)`, koneStart]] : []),
    ['Lift', reference.lift],
    ['Traffic', reference.traffic],
    ['Environment', reference.environment],
  ];
  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">Calibration reference</h2>
          <p className="mt-0.5 text-xs text-steel-500">Every fixed value, and where it comes from.</p>
        </div>
      </header>
      <div className="max-h-96 overflow-y-auto">
        {groups.map(([title, items]) => (
          <div key={title}>
            <p className="bg-steel-50 px-4 py-1.5 text-[0.65rem] font-semibold uppercase tracking-wide text-steel-500">
              {title}
            </p>
            <ul className="divide-y divide-steel-100">
              {Object.entries(items).map(([key, item]) => (
                <li key={key} className="px-4 py-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-navy-900">{humanise(key)}</span>
                    <span className="flex items-center gap-2">
                      <span className="font-mono">
                        {item.value} {item.unit}
                      </span>
                      <span className={cx('badge', SOURCE[item.source]?.chip)}>{SOURCE[item.source]?.label}</span>
                    </span>
                  </div>
                  <p className="mt-0.5 text-[0.7rem] text-steel-500">{item.basis}</p>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

const FOCUS_TYPES = COMPONENTS;

function StartPanel({ sim, onStartFrom, onNewLift }) {
  const [options, setOptions] = useState([]);
  const [chosen, setChosen] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      FOCUS_TYPES.map((type) =>
        componentsApi.list({ component_type: type, page_size: 200 }).then((page) => page.items || []),
      ),
    )
      .then((groups) => {
        if (!cancelled) setOptions(groups.flat());
      })
      .catch(() => {
        if (!cancelled) setOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const current = sim.results?.focus?.component_id;
  return (
    <section className="card">
      <div className="flex flex-wrap items-center gap-3 px-5 py-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-steel-500">Start from</p>
        <button
          type="button"
          className={cx('btn-ghost btn-sm', !current && 'bg-navy-50 text-navy-900')}
          onClick={onNewLift}
        >
          New lift
        </button>
        <span className="text-xs text-steel-400">or a real component:</span>
        <select
          className="select w-auto min-w-[16rem] py-1.5 text-sm"
          value={chosen || current || ''}
          onChange={(event) => setChosen(event.target.value)}
          aria-label="Real component to simulate"
        >
          <option value="">Choose a motor, rope, sheave or governor...</option>
          {FOCUS_TYPES.map((type) => (
            <optgroup key={type} label={type}>
              {options
                .filter((item) => item.component_type === type)
                .map((item) => (
                  <option key={item.component_id} value={item.component_id}>
                    {item.component_id} - {item.location || 'no location'} - {item.component_age?.toFixed(1)} yr
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
        <button
          type="button"
          className="btn-secondary btn-sm"
          disabled={!chosen || sim.busy}
          onClick={() => onStartFrom(chosen)}
        >
          <FlaskConical className="h-4 w-4" />
          Simulate this part
        </button>
      </div>
    </section>
  );
}

function FocusBanner({ focus, sim }) {
  const [name, setName] = useState('');
  const [saved, setSaved] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const implied = focus.implied_load;

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      setSaved(await sim.saveScenario(name));
      setName('');
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-xl border border-navy-200 bg-navy-50 px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl space-y-1 text-sm text-navy-900">
          <p className="font-bold">
            Simulating {focus.component_id} ({focus.component_type})
            {focus.location ? ` at ${focus.location}` : ''} from its real record
          </p>
          <p className="text-xs text-steel-600">{focus.note}</p>
          <p className="text-xs text-steel-600">
            Its recorded equivalent load corresponds to an average car load of{' '}
            <strong>{implied.load_kg.toFixed(0)} kg</strong>
            {implied.alternative_load_kg != null
              ? ` (or ${implied.alternative_load_kg} kg - a motor feels an empty and a full car alike, either side of the counterweight balance)`
              : ''}
            . Starting life used: <strong>{Math.round(focus.starting_wear * 100)}%</strong>.{' '}
            {focus.calibration.note}
          </p>
        </div>
        <div className="min-w-[16rem] space-y-2">
          <div className="flex gap-2">
            <input
              className="input py-1.5 text-sm"
              placeholder="Scenario name (optional)"
              value={name}
              maxLength={96}
              onChange={(event) => setName(event.target.value)}
              aria-label="Scenario name"
            />
            <button type="button" className="btn-accent btn-sm" onClick={save} disabled={saving || sim.running}>
              <Save className="h-4 w-4" />
              {saving ? 'Saving...' : 'Save to passport'}
            </button>
          </div>
          <p className="text-[0.7rem] text-steel-500">
            Saved as a labelled SIMULATION - it never changes the component or any fleet figure.
            {sim.running ? ' Pause to save.' : ''}
          </p>
          {saved ? (
            <p className="text-xs text-emerald-700">
              Saved &quot;{saved.name}&quot;.{' '}
              <Link to={`/components/${focus.component_id}`} className="font-semibold underline">
                View on the component
              </Link>
            </p>
          ) : null}
          {error ? <p className="text-xs text-red-700">{error.message || 'Could not save.'}</p> : null}
        </div>
      </div>
    </section>
  );
}
