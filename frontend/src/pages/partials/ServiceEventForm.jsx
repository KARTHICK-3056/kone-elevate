import { useState } from 'react';
import { componentsApi } from '../../api/client';
import ErrorMessage from '../../components/ErrorMessage';
import { SERVICE_EVENT_TYPES } from '../../utils/constants';

const today = () => new Date().toISOString().slice(0, 10);

/** Records an inspection, maintenance, repair, modernisation or removal event. */
export default function ServiceEventForm({ component, onCreated, onCancel }) {
  const [form, setForm] = useState({
    event_type: 'INSPECTION',
    event_date: today(),
    technician: '',
    description: '',
    operating_hours: component?.operating_hours ?? '',
    vibration: component?.vibration ?? '',
    temperature: component?.temperature ?? '',
    inspection_score: component?.inspection_score ?? '',
    update_component: true,
  });
  const [extraReadings, setExtraReadings] = useState([{ key: '', value: '' }]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const update = (name, value) => setForm((previous) => ({ ...previous, [name]: value }));

  const numeric = (value) => (value === '' || value === null ? undefined : Number(value));

  const updateExtraReading = (index, field, value) =>
    setExtraReadings((rows) => rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)));

  const addExtraReadingRow = () => setExtraReadings((rows) => [...rows, { key: '', value: '' }]);

  const removeExtraReadingRow = (index) =>
    setExtraReadings((rows) => (rows.length > 1 ? rows.filter((_, i) => i !== index) : rows));

  const buildSensorMetadata = () => {
    const entries = extraReadings
      .map((row) => [row.key.trim(), row.value.trim()])
      .filter(([key, value]) => key && value !== '');
    if (!entries.length) return undefined;
    const metadata = {};
    entries.forEach(([key, value]) => {
      const asNumber = Number(value);
      metadata[key] = value !== '' && !Number.isNaN(asNumber) ? asNumber : value;
    });
    return metadata;
  };

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const created = await componentsApi.addServiceEvent(component.component_id, {
        event_type: form.event_type,
        event_date: form.event_date,
        technician: form.technician.trim() || undefined,
        description: form.description.trim() || undefined,
        operating_hours: numeric(form.operating_hours),
        vibration: numeric(form.vibration),
        temperature: numeric(form.temperature),
        inspection_score: numeric(form.inspection_score),
        sensor_metadata: buildSensorMetadata(),
        update_component: form.update_component,
      });
      onCreated?.(created);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      {error ? <ErrorMessage error={error} compact /> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="event_type">
            Event type *
          </label>
          <select
            id="event_type"
            className="select"
            value={form.event_type}
            onChange={(event) => update('event_type', event.target.value)}
          >
            {SERVICE_EVENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="label" htmlFor="event_date">
            Event date *
          </label>
          <input
            id="event_date"
            type="date"
            className="input"
            max={today()}
            value={form.event_date}
            onChange={(event) => update('event_date', event.target.value)}
            required
          />
        </div>

        <div className="sm:col-span-2">
          <label className="label" htmlFor="technician">
            Technician
          </label>
          <input
            id="technician"
            className="input"
            value={form.technician}
            onChange={(event) => update('technician', event.target.value)}
          />
        </div>

        <div className="sm:col-span-2">
          <label className="label" htmlFor="description">
            Description
          </label>
          <textarea
            id="description"
            className="textarea"
            rows={3}
            value={form.description}
            onChange={(event) => update('description', event.target.value)}
            placeholder="What was inspected, adjusted or replaced?"
          />
        </div>
      </div>

      <fieldset className="space-y-3 rounded-lg border border-steel-200 p-3">
        <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-steel-500">
          Readings taken at this visit
        </legend>
        <div className="grid gap-3 sm:grid-cols-4">
          <div>
            <label className="label" htmlFor="operating_hours">
              Hours
            </label>
            <input
              id="operating_hours"
              type="number"
              min="0"
              className="input font-mono"
              value={form.operating_hours}
              onChange={(event) => update('operating_hours', event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="vibration">
              Vibration
            </label>
            <input
              id="vibration"
              type="number"
              step="0.1"
              min="0"
              max="25"
              className="input font-mono"
              value={form.vibration}
              onChange={(event) => update('vibration', event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="temperature">
              Temp (C)
            </label>
            <input
              id="temperature"
              type="number"
              step="0.5"
              className="input font-mono"
              value={form.temperature}
              onChange={(event) => update('temperature', event.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="inspection_score">
              Inspection /100
            </label>
            <input
              id="inspection_score"
              type="number"
              min="0"
              max="100"
              className="input font-mono"
              value={form.inspection_score}
              onChange={(event) => update('inspection_score', event.target.value)}
            />
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm text-steel-700">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-steel-300 text-accent focus:ring-accent"
            checked={form.update_component}
            onChange={(event) => update('update_component', event.target.checked)}
          />
          Apply these readings to the component record
        </label>
      </fieldset>

      <fieldset className="space-y-2 rounded-lg border border-steel-200 p-3">
        <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-steel-500">
          Additional sensor readings (optional)
        </legend>
        <p className="text-[0.7rem] text-steel-400">
          Vendor-specific readings that don&apos;t fit the fields above (e.g. current draw,
          acoustic emission, door-cycle count). Stored as-is alongside this event.
        </p>
        {extraReadings.map((row, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              type="text"
              className="input font-mono text-xs"
              placeholder="reading name, e.g. current_draw_amps"
              value={row.key}
              onChange={(event) => updateExtraReading(index, 'key', event.target.value)}
            />
            <input
              type="text"
              className="input font-mono text-xs"
              placeholder="value"
              value={row.value}
              onChange={(event) => updateExtraReading(index, 'value', event.target.value)}
            />
            <button
              type="button"
              className="btn-secondary btn-sm shrink-0"
              onClick={() => removeExtraReadingRow(index)}
              aria-label="Remove reading"
            >
              &times;
            </button>
          </div>
        ))}
        <button type="button" className="btn-secondary btn-sm" onClick={addExtraReadingRow}>
          + Add reading
        </button>
      </fieldset>

      <p className="text-[0.7rem] text-steel-400">
        Recording an event appends an entry to the tamper-evident audit chain.
      </p>

      <div className="flex justify-end gap-3 border-t border-steel-200 pt-4">
        <button type="button" className="btn-secondary" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
        <button type="submit" className="btn-accent" disabled={submitting}>
          {submitting ? 'Recording...' : 'Record event'}
        </button>
      </div>
    </form>
  );
}
