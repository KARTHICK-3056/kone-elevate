import { useCallback, useEffect, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Download, RadioTower, Upload } from 'lucide-react';
import { fieldDataApi } from '../api/client';
import { downloadBlob, formatDateTime, formatNumber } from '../utils/formatters';

/**
 * Sensor / controller data for one component - the platform's real-world data
 * path that needs no vendor account. A retrofit sensor gateway can POST to the
 * API; a controller export can be uploaded here as CSV.
 */

const TEMPLATE = [
  'recorded_at,trips,run_seconds,load_kg,load_percent,vibration,temperature',
  '2026-09-01T00:00:00Z,310,6820,,46,2.9,54.5',
].join('\n');

export default function FieldDataCard({ componentId, onChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const [source, setSource] = useState('controller-export');
  const [ratedLoad, setRatedLoad] = useState(1000);
  const [result, setResult] = useState(null);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await fieldDataApi.telemetry(componentId));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [componentId]);

  useEffect(() => {
    load();
  }, [load]);

  const upload = async (event) => {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    setResult(null);
    setError(null);
    try {
      const response = await fieldDataApi.uploadCsv(componentId, file, source, ratedLoad);
      setResult(response);
      await load();
      onChanged?.();
    } catch (err) {
      setError(err);
    } finally {
      setUploading(false);
    }
  };

  const monthly = data?.monthly || [];
  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">Sensor and controller data</h2>
          <p className="mt-0.5 text-xs text-steel-500">
            Real usage and condition readings from any source - a retrofit sensor kit, a controller
            export, a monitoring system. No vendor account needed.
          </p>
        </div>
        <RadioTower className="h-5 w-5 text-steel-400" aria-hidden="true" />
      </header>
      <div className="card-body space-y-4">
        {data?.sources?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[0.65rem] uppercase tracking-wide text-steel-500">
                <tr>
                  <th className="py-1 pr-3">Source</th>
                  <th className="py-1 pr-3 text-right">Readings</th>
                  <th className="py-1 pr-3 text-right">Trips</th>
                  <th className="py-1 pr-3">First</th>
                  <th className="py-1">Latest</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-steel-100">
                {data.sources.map((row) => (
                  <tr key={row.source}>
                    <td className="py-1.5 pr-3 font-semibold text-navy-900">{row.source}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{formatNumber(row.readings)}</td>
                    <td className="py-1.5 pr-3 text-right font-mono">{formatNumber(row.trips)}</td>
                    <td className="py-1.5 pr-3">{formatDateTime(row.first)}</td>
                    <td className="py-1.5">{formatDateTime(row.last)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-steel-500">
            No sensor or controller data for this component yet. Its readings come only from service
            visits until a source is connected.
          </p>
        )}

        {monthly.length > 1 ? (
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={monthly} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis dataKey="month" stroke="#8593aa" fontSize={10} />
                <YAxis yAxisId="v" stroke="#8593aa" fontSize={10} />
                <YAxis yAxisId="t" orientation="right" stroke="#8593aa" fontSize={10} />
                <Tooltip contentStyle={{ fontSize: '0.75rem', borderRadius: '0.5rem' }} />
                <Legend wrapperStyle={{ fontSize: '0.7rem' }} />
                <Line yAxisId="v" dataKey="vibration" name="Vibration (mm/s, monthly mean)" stroke="#1a73e8" dot={false} isAnimationActive={false} />
                <Line yAxisId="t" dataKey="temperature" name="Temperature (C, monthly mean)" stroke="#e8710a" dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        <form onSubmit={upload} className="space-y-2 rounded-lg border border-dashed border-steel-300 p-3">
          <p className="text-xs font-semibold text-navy-900">Upload a CSV export</p>
          <div className="flex flex-wrap items-end gap-3">
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
              className="text-xs"
              aria-label="CSV file"
            />
            <label className="text-xs text-steel-600">
              Source
              <input
                className="input mt-1 w-44 py-1 text-sm"
                value={source}
                maxLength={48}
                onChange={(event) => setSource(event.target.value)}
              />
            </label>
            <label className="text-xs text-steel-600">
              Lift rated load (kg)
              <input
                type="number"
                min="1"
                className="input mt-1 w-28 py-1 text-sm"
                value={ratedLoad}
                onChange={(event) => setRatedLoad(Number(event.target.value) || 1000)}
              />
            </label>
            <button type="submit" className="btn-secondary btn-sm" disabled={!file || uploading}>
              <Upload className="h-4 w-4" />
              {uploading ? 'Uploading...' : 'Upload'}
            </button>
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={() => downloadBlob(TEMPLATE, 'telemetry-template.csv')}
            >
              <Download className="h-4 w-4" />
              Template
            </button>
          </div>
          <p className="text-[0.7rem] text-steel-500">
            Columns: {(data?.csv_columns || []).join(', ')}. <code>trips</code> and{' '}
            <code>run_seconds</code> are counts since the previous row. Re-uploading the same rows is
            safe - they are recognised and ignored.
          </p>
        </form>

        {result ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
            <p className="font-semibold">
              {result.accepted} readings accepted, {result.duplicates_ignored} duplicates ignored,{' '}
              {result.rejected_count + (result.csv_error_count || 0)} rejected.
            </p>
            <p>
              +{formatNumber(result.trips_added)} trips, +{result.run_hours_added} running hours.
              {Object.keys(result.component_updates).length
                ? ` Updated: ${Object.keys(result.component_updates).join(', ')}.`
                : ''}
            </p>
            {[...(result.rejected || []), ...(result.csv_errors || [])].slice(0, 5).map((row) => (
              <p key={`${row.row || row.line}-${row.reason}`} className="text-amber-800">
                {row.row ? `Row ${row.row}` : `Line ${row.line}`}: {row.reason}
              </p>
            ))}
          </div>
        ) : null}
        {error ? <p className="text-xs text-red-700">{error.message}</p> : null}
      </div>
    </section>
  );
}
