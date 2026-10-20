import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { componentsApi, platformApi } from '../../api/client';
import ErrorMessage from '../../components/ErrorMessage';
import { COMPONENT_TYPES, MATERIALS, isSafetyCritical } from '../../utils/constants';

const EMPTY = {
  component_type: 'Motor',
  material: 'Steel',
  material_grade: '',
  serial_number: '',
  manufacturer: '',
  origin: '',
  location: '',
  installation_date: '',
  operating_hours: 0,
  load_cycles: 0,
  average_load: 0,
  vibration: 0,
  temperature: 25,
  service_count: 0,
  repair_count: 0,
  failure_history: 0,
  inspection_score: 100,
  notes: '',
  run_initial_prediction: true,
};

const NUMERIC_FIELDS = [
  { name: 'operating_hours', label: 'Operating hours', unit: 'h', step: 1, min: 0 },
  { name: 'load_cycles', label: 'Load cycles', unit: 'cycles', step: 1, min: 0 },
  { name: 'average_load', label: 'Average load', unit: 'kg', step: 1, min: 0 },
  { name: 'vibration', label: 'Vibration', unit: 'mm/s RMS', step: 0.1, min: 0, max: 25 },
  { name: 'temperature', label: 'Temperature', unit: 'C', step: 0.5, min: -40, max: 150 },
  { name: 'service_count', label: 'Service count', unit: 'visits', step: 1, min: 0 },
  { name: 'repair_count', label: 'Repair count', unit: 'repairs', step: 1, min: 0 },
  { name: 'failure_history', label: 'Recorded failures', unit: 'events', step: 1, min: 0 },
  { name: 'inspection_score', label: 'Inspection score', unit: '/100', step: 1, min: 0, max: 100 },
];

/** Component registration form with client-side and server-side validation. */
export default function AddComponentForm({ onCreated, onCancel }) {
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [gradeCatalogue, setGradeCatalogue] = useState({});

  useEffect(() => {
    let cancelled = false;
    platformApi
      .enums()
      .then((data) => {
        if (!cancelled) setGradeCatalogue(data.material_grades || {});
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Only grades valid for this type and material can be recorded.
  const grades = (gradeCatalogue[form.component_type] || []).filter((grade) =>
    grade.materials.includes(form.material),
  );
  const selectedGrade = grades.find((grade) => grade.grade === form.material_grade);

  const update = (name, value) =>
    setForm((previous) => ({
      ...previous,
      [name]: value,
      // A grade recorded for another type or material no longer applies.
      ...(name === 'component_type' || name === 'material' ? { material_grade: '' } : {}),
    }));

  const validate = () => {
    const issues = {};
    if (!form.component_type) issues.component_type = 'Select a component type';
    if (!form.material) issues.material = 'Select a material';
    if (form.installation_date && new Date(form.installation_date) > new Date()) {
      issues.installation_date = 'Installation date cannot be in the future';
    }
    if (form.inspection_score < 0 || form.inspection_score > 100) {
      issues.inspection_score = 'Inspection score must be between 0 and 100';
    }
    NUMERIC_FIELDS.forEach((field) => {
      if (Number(form[field.name]) < (field.min ?? 0)) {
        issues[field.name] = `${field.label} cannot be negative`;
      }
    });
    setFieldErrors(issues);
    return Object.keys(issues).length === 0;
  };

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      const payload = {
        ...form,
        serial_number: form.serial_number.trim() || undefined,
        manufacturer: form.manufacturer.trim() || undefined,
        origin: form.origin.trim() || undefined,
        location: form.location.trim() || undefined,
        notes: form.notes.trim() || undefined,
        material_grade: form.material_grade || undefined,
        installation_date: form.installation_date || undefined,
        operating_hours: Number(form.operating_hours),
        load_cycles: Number(form.load_cycles),
        average_load: Number(form.average_load),
        vibration: Number(form.vibration),
        temperature: Number(form.temperature),
        service_count: Number(form.service_count),
        repair_count: Number(form.repair_count),
        failure_history: Number(form.failure_history),
        inspection_score: Number(form.inspection_score),
      };
      const created = await componentsApi.create(payload);
      onCreated?.(created);
      setForm(EMPTY);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const safety = isSafetyCritical(form.component_type);

  return (
    <form onSubmit={submit} className="space-y-5">
      {error ? <ErrorMessage error={error} compact /> : null}

      {safety ? (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            <strong>{form.component_type}</strong> is a safety-critical component type. Every AI
            assessment for it will carry a MANDATORY HUMAN INSPECTION requirement.
          </span>
        </div>
      ) : null}

      {/* ------------------------------------------------------- identity */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-bold text-navy-900">Identity</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="component_type">
              Component type *
            </label>
            <select
              id="component_type"
              className="select"
              value={form.component_type}
              onChange={(event) => update('component_type', event.target.value)}
              required
            >
              {COMPONENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            {fieldErrors.component_type ? (
              <p className="field-error">{fieldErrors.component_type}</p>
            ) : null}
          </div>

          <div>
            <label className="label" htmlFor="material">
              Material *
            </label>
            <select
              id="material"
              className="select"
              value={form.material}
              onChange={(event) => update('material', event.target.value)}
              required
            >
              {MATERIALS.map((material) => (
                <option key={material} value={material}>
                  {material}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="material_grade">
              Material grade
            </label>
            <select
              id="material_grade"
              className="select"
              value={form.material_grade}
              onChange={(event) => update('material_grade', event.target.value)}
              disabled={!grades.length}
            >
              <option value="">Not recorded - use industry standard</option>
              {grades.map((grade) => (
                <option key={grade.grade} value={grade.grade}>
                  {grade.designation ? `${grade.designation} — ${grade.label}` : grade.label}
                </option>
              ))}
            </select>
            {selectedGrade?.grading_system ? (
              <p className="mt-1 text-[0.7rem] font-medium text-navy-800">
                Graded under: {selectedGrade.grading_system}
              </p>
            ) : null}
            <p className="mt-1 text-[0.7rem] text-steel-500">
              {grades.length
                ? 'Record the grade from the nameplate or bill of materials. If unknown, the industry-standard grade for the material is assumed and labelled as such.'
                : `No grades are catalogued for a ${form.material} ${form.component_type}.`}
            </p>
          </div>

          <div>
            <label className="label" htmlFor="serial_number">
              Serial number
            </label>
            <input
              id="serial_number"
              className="input font-mono"
              placeholder="Auto-generated if left blank"
              value={form.serial_number}
              onChange={(event) => update('serial_number', event.target.value)}
            />
          </div>

          <div>
            <label className="label" htmlFor="manufacturer">
              Manufacturer / product line
            </label>
            <input
              id="manufacturer"
              className="input"
              value={form.manufacturer}
              onChange={(event) => update('manufacturer', event.target.value)}
            />
          </div>

          <div>
            <label className="label" htmlFor="origin">
              Origin (plant)
            </label>
            <input
              id="origin"
              className="input"
              value={form.origin}
              onChange={(event) => update('origin', event.target.value)}
            />
          </div>

          <div>
            <label className="label" htmlFor="location">
              Current location
            </label>
            <input
              id="location"
              className="input"
              placeholder="Chennai, India"
              value={form.location}
              onChange={(event) => update('location', event.target.value)}
            />
          </div>

          <div>
            <label className="label" htmlFor="installation_date">
              Installation date
            </label>
            <input
              id="installation_date"
              type="date"
              className="input"
              max={new Date().toISOString().slice(0, 10)}
              value={form.installation_date}
              onChange={(event) => update('installation_date', event.target.value)}
            />
            {fieldErrors.installation_date ? (
              <p className="field-error">{fieldErrors.installation_date}</p>
            ) : null}
          </div>
        </div>
      </fieldset>

      {/* ------------------------------------------- operating and service */}
      <fieldset className="space-y-3">
        <legend className="text-sm font-bold text-navy-900">Operating and service history</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          {NUMERIC_FIELDS.map((field) => (
            <div key={field.name}>
              <label className="label" htmlFor={field.name}>
                {field.label} <span className="normal-case text-steel-400">({field.unit})</span>
              </label>
              <input
                id={field.name}
                type="number"
                className="input font-mono"
                step={field.step}
                min={field.min}
                max={field.max}
                value={form[field.name]}
                onChange={(event) => update(field.name, event.target.value)}
              />
              {fieldErrors[field.name] ? (
                <p className="field-error">{fieldErrors[field.name]}</p>
              ) : null}
            </div>
          ))}
        </div>
      </fieldset>

      <div>
        <label className="label" htmlFor="notes">
          Notes
        </label>
        <textarea
          id="notes"
          className="textarea"
          rows={2}
          maxLength={512}
          value={form.notes}
          onChange={(event) => update('notes', event.target.value)}
        />
      </div>

      <label className="flex items-center gap-2 text-sm text-steel-700">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border-steel-300 text-accent focus:ring-accent"
          checked={form.run_initial_prediction}
          onChange={(event) => update('run_initial_prediction', event.target.checked)}
        />
        Run an initial AI assessment after registration
      </label>

      <div className="flex justify-end gap-3 border-t border-steel-200 pt-4">
        <button type="button" className="btn-secondary" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
        <button type="submit" className="btn-accent" disabled={submitting}>
          {submitting ? 'Registering...' : 'Register component'}
        </button>
      </div>
    </form>
  );
}
