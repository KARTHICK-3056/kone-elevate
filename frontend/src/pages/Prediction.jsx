import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Brain, Database, Gauge, RotateCcw, Search } from 'lucide-react';
import { componentsApi } from '../api/client';
import { usePrediction, useModelInfo } from '../hooks/usePrediction';
import PredictionCard from '../components/PredictionCard';
import ErrorMessage, { NoticeBanner } from '../components/ErrorMessage';
import Loading from '../components/Loading';
import { COMPONENT_TYPES, MATERIALS, isSafetyCritical } from '../utils/constants';
import { formatPercent, humanise } from '../utils/formatters';

const PRESETS = {
  healthy: {
    label: 'Healthy motor',
    values: {
      component_type: 'Motor',
      material: 'Steel',
      component_age: 3,
      operating_hours: 9600,
      load_cycles: 190000,
      average_load: 520,
      vibration: 1.6,
      temperature: 42,
      service_count: 7,
      repair_count: 0,
      failure_history: 0,
      inspection_score: 94,
      days_since_last_service: 45,
    },
  },
  moderate: {
    label: 'Moderately degraded motor',
    values: {
      component_type: 'Motor',
      material: 'Steel',
      component_age: 12.5,
      operating_hours: 47000,
      load_cycles: 980000,
      average_load: 810,
      vibration: 4.6,
      temperature: 63,
      service_count: 18,
      repair_count: 2,
      failure_history: 0,
      inspection_score: 63,
      days_since_last_service: 210,
    },
  },
  heavy: {
    label: 'Heavily degraded sheave',
    values: {
      component_type: 'Sheave',
      material: 'Cast Iron',
      component_age: 22,
      operating_hours: 78000,
      load_cycles: 1500000,
      average_load: 1450,
      vibration: 5.4,
      temperature: 68,
      service_count: 24,
      repair_count: 4,
      failure_history: 1,
      inspection_score: 42,
      days_since_last_service: 420,
    },
  },
  rope: {
    label: 'Safety-critical steel rope',
    values: {
      component_type: 'Steel Rope',
      material: 'Steel',
      component_age: 2.2,
      operating_hours: 8400,
      load_cycles: 240000,
      average_load: 880,
      vibration: 1.2,
      temperature: 33,
      service_count: 5,
      repair_count: 0,
      failure_history: 0,
      inspection_score: 95,
      days_since_last_service: 28,
    },
  },
  brake: {
    label: 'Safety-critical brake, worn lining',
    values: {
      component_type: 'Brake',
      material: 'Cast Iron',
      component_age: 8,
      operating_hours: 33000,
      load_cycles: 820000,
      average_load: 980,
      vibration: 2.2,
      temperature: 62,
      service_count: 18,
      repair_count: 1,
      failure_history: 0,
      inspection_score: 66,
      days_since_last_service: 150,
    },
  },
};

const NUMERIC_FIELDS = [
  { name: 'component_age', label: 'Component age', unit: 'years', step: 0.1, min: 0, max: 60 },
  { name: 'operating_hours', label: 'Operating hours', unit: 'h', step: 100, min: 0 },
  { name: 'load_cycles', label: 'Load cycles', unit: 'cycles', step: 1000, min: 0 },
  { name: 'average_load', label: 'Average load', unit: 'kg', step: 10, min: 0 },
  { name: 'vibration', label: 'Vibration', unit: 'mm/s RMS', step: 0.1, min: 0, max: 25 },
  { name: 'temperature', label: 'Temperature', unit: 'C', step: 1, min: -40, max: 150 },
  { name: 'service_count', label: 'Service visits', unit: 'count', step: 1, min: 0 },
  { name: 'repair_count', label: 'Repairs', unit: 'count', step: 1, min: 0 },
  { name: 'failure_history', label: 'Failures', unit: 'count', step: 1, min: 0 },
  { name: 'inspection_score', label: 'Inspection score', unit: '/100', step: 1, min: 0, max: 100 },
  { name: 'days_since_last_service', label: 'Days since service', unit: 'days', step: 1, min: 0 },
];

/** AI Circular Intelligence workspace: assess a stored component or a payload. */
export default function Prediction() {
  const { componentId } = useParams();
  const [mode, setMode] = useState(componentId ? 'existing' : 'manual');
  const [form, setForm] = useState(PRESETS.moderate.values);
  const [lookup, setLookup] = useState(componentId || '');
  const [componentOptions, setComponentOptions] = useState([]);

  const { prediction, loading, error, predictPayload, predictComponent, reset } = usePrediction();
  const { info, metrics } = useModelInfo();

  // Offer a short list of components for the picker.
  useEffect(() => {
    componentsApi
      .list({ page_size: 50, sort_by: 'component_id' })
      .then((data) => setComponentOptions(data.items || []))
      .catch(() => setComponentOptions([]));
  }, []);

  useEffect(() => {
    if (componentId) {
      setMode('existing');
      setLookup(componentId);
      predictComponent(componentId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [componentId]);

  const update = (name, value) => setForm((previous) => ({ ...previous, [name]: value }));

  const submitManual = async (event) => {
    event.preventDefault();
    const payload = { ...form };
    NUMERIC_FIELDS.forEach((field) => {
      payload[field.name] = Number(payload[field.name]);
    });
    payload.load_cycles = Math.round(payload.load_cycles);
    payload.service_count = Math.round(payload.service_count);
    payload.repair_count = Math.round(payload.repair_count);
    payload.failure_history = Math.round(payload.failure_history);
    payload.days_since_last_service = Math.round(payload.days_since_last_service);
    await predictPayload(payload);
  };

  const submitExisting = async (event) => {
    event.preventDefault();
    if (!lookup.trim()) return;
    await predictComponent(lookup.trim());
  };

  const safety = isSafetyCritical(form.component_type);

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-navy-900">AI Prediction</h1>
          <p className="mt-1 text-sm text-steel-500">
            Assess a component and get an explainable, advisory end-of-use recommendation.
          </p>
        </div>
        {info ? (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="badge-outline">
              <Database className="h-3 w-3" aria-hidden="true" />
              {info.model_version}
            </span>
            {info.accuracy ? (
              <span className="badge-outline">
                <Gauge className="h-3 w-3" aria-hidden="true" />
                Test accuracy {formatPercent(info.accuracy, 1)}
              </span>
            ) : null}
            <span className="badge bg-amber-100 text-amber-900">Synthetic training data</span>
          </div>
        ) : null}
      </header>

      {info && !info.model_available ? (
        <NoticeBanner>
          No trained model is loaded, so assessments fall back to the transparent health-score
          heuristic. Train one with{' '}
          <code className="font-mono">python scripts/train_model.py</code> in{' '}
          <code className="font-mono">backend/</code>.
        </NoticeBanner>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-5">
        {/* ------------------------------------------------------- input */}
        <div className="space-y-4 lg:col-span-2">
          <div className="card">
            <div className="flex border-b border-steel-200">
              <button
                type="button"
                onClick={() => setMode('existing')}
                className={`flex-1 px-4 py-3 text-sm font-semibold ${
                  mode === 'existing'
                    ? 'border-b-2 border-accent text-navy-900'
                    : 'text-steel-500 hover:text-navy-800'
                }`}
              >
                Existing component
              </button>
              <button
                type="button"
                onClick={() => setMode('manual')}
                className={`flex-1 px-4 py-3 text-sm font-semibold ${
                  mode === 'manual'
                    ? 'border-b-2 border-accent text-navy-900'
                    : 'text-steel-500 hover:text-navy-800'
                }`}
              >
                Manual entry
              </button>
            </div>

            {mode === 'existing' ? (
              <form onSubmit={submitExisting} className="card-body space-y-3">
                <div>
                  <label className="label" htmlFor="component-lookup">
                    Component identifier
                  </label>
                  <input
                    id="component-lookup"
                    className="input font-mono"
                    list="component-options"
                    placeholder="KE-MOT-000001"
                    value={lookup}
                    onChange={(event) => setLookup(event.target.value)}
                  />
                  <datalist id="component-options">
                    {componentOptions.map((option) => (
                      <option key={option.component_id} value={option.component_id}>
                        {option.component_type} - {option.current_status}
                      </option>
                    ))}
                  </datalist>
                  <p className="mt-1 text-[0.7rem] text-steel-400">
                    Assessing a stored component saves an immutable prediction and appends an audit
                    record.
                  </p>
                </div>

                <button type="submit" className="btn-accent w-full" disabled={loading || !lookup.trim()}>
                  <Brain className="h-4 w-4" aria-hidden="true" />
                  {loading ? 'Assessing...' : 'Run AI assessment'}
                </button>
              </form>
            ) : (
              <form onSubmit={submitManual} className="card-body space-y-4">
                <div>
                  <p className="label">Demo presets</p>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(PRESETS).map(([key, preset]) => (
                      <button
                        key={key}
                        type="button"
                        className="btn-secondary btn-sm"
                        onClick={() => {
                          setForm(preset.values);
                          reset();
                        }}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="label" htmlFor="pred-type">
                      Component type
                    </label>
                    <select
                      id="pred-type"
                      className="select"
                      value={form.component_type}
                      onChange={(event) => update('component_type', event.target.value)}
                    >
                      {COMPONENT_TYPES.map((type) => (
                        <option key={type} value={type}>
                          {type}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="label" htmlFor="pred-material">
                      Material
                    </label>
                    <select
                      id="pred-material"
                      className="select"
                      value={form.material}
                      onChange={(event) => update('material', event.target.value)}
                    >
                      {MATERIALS.map((material) => (
                        <option key={material} value={material}>
                          {material}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {safety ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-800">
                    {form.component_type} is safety-critical: the result will carry a MANDATORY HUMAN
                    INSPECTION requirement.
                  </div>
                ) : null}

                <div className="grid gap-3 sm:grid-cols-2">
                  {NUMERIC_FIELDS.map((field) => (
                    <div key={field.name}>
                      <label className="label" htmlFor={`pred-${field.name}`}>
                        {field.label}{' '}
                        <span className="normal-case text-steel-400">({field.unit})</span>
                      </label>
                      <input
                        id={`pred-${field.name}`}
                        type="number"
                        className="input font-mono"
                        step={field.step}
                        min={field.min}
                        max={field.max}
                        value={form[field.name]}
                        onChange={(event) => update(field.name, event.target.value)}
                      />
                    </div>
                  ))}
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setForm(PRESETS.moderate.values);
                      reset();
                    }}
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    Reset
                  </button>
                  <button type="submit" className="btn-accent flex-1" disabled={loading}>
                    <Brain className="h-4 w-4" aria-hidden="true" />
                    {loading ? 'Assessing...' : 'Assess component'}
                  </button>
                </div>
              </form>
            )}
          </div>

          {metrics ? (
            <section className="card">
              <header className="card-header">
                <h2 className="card-title">Model performance</h2>
              </header>
              <div className="card-body space-y-2 text-sm">
                <Metric label="Accuracy" value={formatPercent(metrics.accuracy, 2)} />
                <Metric label="F1 (macro)" value={formatPercent(metrics.f1_macro, 2)} />
                <Metric label="Precision (macro)" value={formatPercent(metrics.precision_macro, 2)} />
                <Metric label="Recall (macro)" value={formatPercent(metrics.recall_macro, 2)} />
                {metrics.cv_f1_macro_mean ? (
                  <Metric
                    label="Cross-validated F1"
                    value={`${formatPercent(metrics.cv_f1_macro_mean, 2)} (+/- ${(
                      metrics.cv_f1_macro_std * 100
                    ).toFixed(2)})`}
                  />
                ) : null}
                <Metric label="Training records" value={metrics.training_records?.toLocaleString()} />
                <Metric label="Data source" value={humanise(metrics.data_source)} />
                <p className="pt-2 text-[0.7rem] text-steel-400">
                  Metrics are measured on a held-out split of the synthetic dataset. They describe
                  performance on simulated degradation, not on real KONE removals.
                </p>
              </div>
            </section>
          ) : null}
        </div>

        {/* ------------------------------------------------------ result */}
        <div className="lg:col-span-3">
          {error ? <ErrorMessage error={error} className="mb-4" /> : null}

          {loading && !prediction ? (
            <Loading label="Running AI assessment..." />
          ) : prediction ? (
            <PredictionCard prediction={prediction} />
          ) : (
            <div className="card flex min-h-[320px] flex-col items-center justify-center gap-3 p-8 text-center">
              <span className="rounded-full bg-steel-100 p-4 text-steel-400">
                <Search className="h-8 w-8" aria-hidden="true" />
              </span>
              <h2 className="text-base font-semibold text-navy-900">No assessment yet</h2>
              <p className="max-w-md text-sm text-steel-500">
                Pick a stored component or enter readings manually, then run the assessment. You will
                get a recommendation category, a confidence figure, a transparent health score and the ranked
                factors behind the result.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-steel-100 pb-1.5">
      <span className="text-steel-500">{label}</span>
      <span className="font-mono font-semibold text-navy-900">{value ?? '-'}</span>
    </div>
  );
}
