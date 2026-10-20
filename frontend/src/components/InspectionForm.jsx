import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ClipboardCheck } from 'lucide-react';
import { fieldDataApi } from '../api/client';
import { cx } from '../utils/formatters';

/**
 * Measured inspection: the technician enters what they measured, the score is
 * computed from it against each measurement's limit (worst one governs).
 * Checklist, limits and their basis come from the backend (app.ml.inspection).
 */

/** Items computed from inputs a technician actually measures. */
const HELPERS = {
  rope_diameter_reduction_pct: [
    { key: 'nominal_diameter_mm', label: 'Nominal diameter', unit: 'mm' },
    { key: 'measured_diameter_mm', label: 'Measured diameter', unit: 'mm' },
  ],
  lining_wear_pct: [
    { key: 'lining_new_mm', label: 'New thickness', unit: 'mm' },
    { key: 'lining_minimum_mm', label: 'Minimum (manufacturer)', unit: 'mm' },
    { key: 'lining_measured_mm', label: 'Measured thickness', unit: 'mm' },
  ],
};

const VERIFICATION = {
  PROTOTYPE_DEFAULT: { label: 'Prototype default limit', chip: 'bg-amber-100 text-amber-900' },
  MANUFACTURER: { label: 'Manufacturer limit', chip: 'bg-sky-100 text-sky-800' },
};

function buildMeasurements(items, values) {
  const out = {};
  items.forEach((item) => {
    const helpers = HELPERS[item.key];
    if (helpers) {
      const filled = helpers.every((h) => values[h.key] !== undefined && values[h.key] !== '');
      if (filled) helpers.forEach((h) => { out[h.key] = Number(values[h.key]); });
      return;
    }
    const value = values[item.key];
    if (value === undefined || value === '') return;
    if (item.kind === 'numeric') out[item.key] = Number(value);
    else if (item.kind === 'pass_fail') out[item.key] = value === 'pass';
    else out[item.key] = value;
  });
  return out;
}

export default function InspectionForm({ component, onSaved, onCancel }) {
  // undefined while loading; null when this type has no checklist.
  const [checklist, setChecklist] = useState(undefined);
  const [values, setValues] = useState({});
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState(null);
  const [notes, setNotes] = useState('');
  const [eventDate, setEventDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fieldDataApi
      .checklists()
      .then((all) => setChecklist(all[component.component_type] || null))
      .catch(setError);
  }, [component.component_type]);

  const items = useMemo(() => checklist?.items || [], [checklist]);
  const measurements = useMemo(() => buildMeasurements(items, values), [items, values]);
  const measurementKey = JSON.stringify(measurements);

  // Live score as the technician types.
  useEffect(() => {
    if (!checklist || !Object.keys(measurements).length) {
      setPreview(null);
      return undefined;
    }
    const timer = setTimeout(() => {
      fieldDataApi
        .preview(component.component_type, measurements)
        .then((result) => {
          setPreview(result);
          setPreviewError(null);
        })
        .catch((err) => setPreviewError(err));
    }, 350);
    return () => clearTimeout(timer);
    // measurementKey stands in for the measurements object's contents.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measurementKey, checklist, component.component_type]);

  const set = (key, value) => setValues((previous) => ({ ...previous, [key]: value }));

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const result = await fieldDataApi.recordInspection(component.component_id, {
        measurements,
        event_date: eventDate,
        notes: notes || undefined,
      });
      onSaved?.(result);
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  };

  if (error && !checklist) return <p className="text-sm text-red-700">{error.message}</p>;
  if (!checklist) {
    return (
      <p className="text-sm text-steel-500">
        {checklist === undefined ? 'Loading checklist...' : `No measurement checklist for ${component.component_type} yet.`}
      </p>
    );
  }

  const byKey = Object.fromEntries((preview?.measurements || []).map((m) => [m.key, m]));

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-xs text-steel-600">{checklist.scoring}</p>

      <div className="space-y-3">
        {items.map((item) => {
          const scored = byKey[item.key];
          return (
            <div key={item.key} className="rounded-lg border border-steel-200 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-navy-900">
                    {item.label}
                    {item.unit ? <span className="ml-1 text-xs font-normal text-steel-500">({item.unit})</span> : null}
                  </p>
                  <p className="text-[0.7rem] text-steel-500">{item.how_measured}</p>
                </div>
                <span className={cx('badge', VERIFICATION[item.verification]?.chip)}>
                  {VERIFICATION[item.verification]?.label}
                </span>
              </div>

              <div className="mt-2 flex flex-wrap items-end gap-3">
                {HELPERS[item.key] ? (
                  HELPERS[item.key].map((helper) => (
                    <label key={helper.key} className="text-xs text-steel-600">
                      {helper.label} ({helper.unit})
                      <input
                        type="number"
                        step="any"
                        min="0"
                        className="input mt-1 w-32 py-1 text-sm"
                        value={values[helper.key] ?? ''}
                        onChange={(event) => set(helper.key, event.target.value)}
                      />
                    </label>
                  ))
                ) : item.kind === 'numeric' ? (
                  <label className="text-xs text-steel-600">
                    Measured
                    <input
                      type="number"
                      step="any"
                      className="input mt-1 w-32 py-1 text-sm"
                      value={values[item.key] ?? ''}
                      onChange={(event) => set(item.key, event.target.value)}
                      aria-label={item.label}
                    />
                  </label>
                ) : item.kind === 'pass_fail' ? (
                  <select
                    className="select w-40 py-1 text-sm"
                    value={values[item.key] ?? ''}
                    onChange={(event) => set(item.key, event.target.value)}
                    aria-label={item.label}
                  >
                    <option value="">Not checked</option>
                    <option value="pass">Pass</option>
                    <option value="fail">Fail</option>
                  </select>
                ) : (
                  <select
                    className="select w-64 py-1 text-sm"
                    value={values[item.key] ?? ''}
                    onChange={(event) => set(item.key, event.target.value)}
                    aria-label={item.label}
                  >
                    <option value="">Not checked</option>
                    {item.options.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.value}
                      </option>
                    ))}
                  </select>
                )}
                {item.kind === 'numeric' ? (
                  <p className="text-[0.7rem] text-steel-500">
                    new {item.new} - limit {item.limit} {item.unit}
                  </p>
                ) : null}
                {scored ? (
                  <div className="min-w-[8rem] flex-1">
                    <div className="h-1.5 overflow-hidden rounded-full bg-steel-100">
                      <div
                        className={cx(
                          'h-full rounded-full',
                          scored.consumption >= 1 ? 'bg-red-600' : scored.consumption >= 0.5 ? 'bg-amber-500' : 'bg-emerald-500',
                        )}
                        style={{ width: `${Math.min(100, scored.consumption * 100)}%` }}
                      />
                    </div>
                    <p className="mt-0.5 text-[0.65rem] text-steel-500">
                      {Math.round(scored.consumption * 100)}% of the way to the limit
                    </p>
                  </div>
                ) : null}
              </div>
              <p className="mt-1 text-[0.65rem] text-steel-400">{item.basis}</p>
            </div>
          );
        })}
      </div>

      {preview ? (
        <div
          className={cx(
            'rounded-lg border px-4 py-3',
            preview.discard_criteria_met.length
              ? 'border-red-300 bg-red-50 text-red-900'
              : preview.band === 'amber'
                ? 'border-amber-200 bg-amber-50 text-amber-900'
                : 'border-emerald-200 bg-emerald-50 text-emerald-900',
          )}
        >
          <p className="flex items-center gap-2 text-sm font-bold">
            <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
            Inspection score {preview.inspection_score}/100 - governed by {preview.governing.label.toLowerCase()}
          </p>
          {preview.discard_criteria_met.length ? (
            <p className="mt-1 flex items-center gap-1 text-xs font-semibold">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
              Discard criterion met: {preview.discard_criteria_met.join('; ')}
            </p>
          ) : null}
          {preview.not_measured.length ? (
            <p className="mt-1 text-[0.7rem]">Not measured: {preview.not_measured.join(', ')}</p>
          ) : null}
        </div>
      ) : null}
      {previewError ? <p className="text-xs text-red-700">{previewError.message}</p> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-steel-600">
          Inspection date
          <input
            type="date"
            className="input mt-1 py-1 text-sm"
            value={eventDate}
            onChange={(event) => setEventDate(event.target.value)}
          />
        </label>
        <label className="text-xs text-steel-600">
          Notes
          <input
            className="input mt-1 py-1 text-sm"
            value={notes}
            maxLength={1500}
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>
      </div>
      <p className="text-[0.7rem] text-amber-800">{checklist.notice}</p>
      {error ? <p className="text-sm text-red-700">{error.message}</p> : null}

      <div className="flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn-accent" disabled={saving || !preview}>
          {saving ? 'Recording...' : 'Record inspection'}
        </button>
      </div>
    </form>
  );
}
