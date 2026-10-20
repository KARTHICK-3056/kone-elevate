import {
  ClipboardCheck,
  PackageMinus,
  PlugZap,
  Search,
  Wrench,
  Hammer,
} from 'lucide-react';
import { cx, formatDate, formatNumber, humanise } from '../utils/formatters';
import { EmptyState } from './ErrorMessage';

const EVENT_STYLE = {
  INSTALLATION: { icon: PlugZap, dot: 'bg-navy-700', badge: 'bg-navy-100 text-navy-800' },
  INSPECTION: { icon: Search, dot: 'bg-blue-500', badge: 'bg-blue-100 text-blue-800' },
  MAINTENANCE: { icon: Wrench, dot: 'bg-emerald-500', badge: 'bg-emerald-100 text-emerald-800' },
  REPAIR: { icon: Hammer, dot: 'bg-amber-500', badge: 'bg-amber-100 text-amber-900' },
  MODERNIZATION: { icon: ClipboardCheck, dot: 'bg-cyan-500', badge: 'bg-cyan-100 text-cyan-800' },
  REMOVAL: { icon: PackageMinus, dot: 'bg-red-500', badge: 'bg-red-100 text-red-800' },
};

/** Vertical timeline of a component's service, inspection and repair history. */
export default function ServiceTimeline({ events = [], emptyAction }) {
  if (!events.length) {
    return (
      <EmptyState
        title="No service history recorded"
        description="Add an inspection, maintenance, repair or removal event to start the lifecycle record."
        action={emptyAction}
        icon={Wrench}
      />
    );
  }

  return (
    <ol className="relative space-y-5 pl-6">
      <span className="absolute left-[7px] top-2 h-[calc(100%-1rem)] w-px bg-steel-200" aria-hidden="true" />

      {events.map((event) => {
        const style = EVENT_STYLE[event.event_type] || EVENT_STYLE.MAINTENANCE;
        const Icon = style.icon;

        return (
          <li key={event.id} className="relative">
            <span
              className={cx(
                'absolute -left-6 top-1 h-4 w-4 rounded-full ring-4 ring-white',
                style.dot,
              )}
              aria-hidden="true"
            />
            <div className="rounded-lg border border-steel-200 bg-white p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className={cx('badge', style.badge)}>
                  <Icon className="h-3 w-3" aria-hidden="true" />
                  {humanise(event.event_type)}
                </span>
                <span className="text-xs font-semibold text-navy-900">
                  {formatDate(event.event_date)}
                </span>
                {event.technician ? (
                  <span className="text-xs text-steel-500">by {event.technician}</span>
                ) : null}
              </div>

              {event.description ? (
                <p className="mt-2 text-sm text-steel-600">{event.description}</p>
              ) : null}

              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.7rem] text-steel-500">
                {event.operating_hours !== null && event.operating_hours !== undefined ? (
                  <span>
                    Hours: <span className="font-mono">{formatNumber(event.operating_hours)}</span>
                  </span>
                ) : null}
                {event.vibration !== null && event.vibration !== undefined ? (
                  <span>
                    Vibration: <span className="font-mono">{event.vibration} mm/s</span>
                  </span>
                ) : null}
                {event.temperature !== null && event.temperature !== undefined ? (
                  <span>
                    Temp: <span className="font-mono">{event.temperature} C</span>
                  </span>
                ) : null}
                {event.inspection_score !== null && event.inspection_score !== undefined ? (
                  <span>
                    Inspection: <span className="font-mono">{event.inspection_score}/100</span>
                  </span>
                ) : null}
                {event.sensor_metadata && Object.keys(event.sensor_metadata).length ? (
                  Object.entries(event.sensor_metadata).map(([key, value]) => (
                    <span key={key}>
                      {humanise(key)}: <span className="font-mono">{String(value)}</span>
                    </span>
                  ))
                ) : null}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Compact list of previous AI assessments. */
export function PredictionTimeline({ predictions = [] }) {
  if (!predictions.length) {
    return (
      <EmptyState
        title="No AI assessment yet"
        description="Run an AI assessment to generate an end-of-use recommendation for this component."
      />
    );
  }

  return (
    <ul className="divide-y divide-steel-100">
      {predictions.map((prediction) => (
        <li key={prediction.id} className="flex flex-wrap items-center gap-3 py-3">
          <span className="font-mono text-xs text-steel-500">
            {formatDate(prediction.predicted_at)}
          </span>
          <span className="text-sm font-bold text-navy-900">{humanise(prediction.recommendation)}</span>
          <span className="text-xs text-steel-500">
            confidence {(prediction.confidence * 100).toFixed(1)}%
          </span>
          <span className="text-xs text-steel-500">health {prediction.health_score}</span>
          {prediction.safety_flag ? (
            <span className="badge bg-red-100 text-red-800">Inspection required</span>
          ) : null}
          <span className="ml-auto font-mono text-[0.65rem] text-steel-400">
            {prediction.model_version}
          </span>
        </li>
      ))}
    </ul>
  );
}
