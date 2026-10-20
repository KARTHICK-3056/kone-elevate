import { Link } from 'react-router-dom';
import { Boxes, Calendar, MapPin, QrCode } from 'lucide-react';
import { isSafetyCritical } from '../utils/constants';
import { formatAge, formatDate, materialWithGrade } from '../utils/formatters';
import HealthBadge, { RecommendationBadge, SafetyChip, StatusBadge } from './HealthBadge';

/** Card view of a component, used on mobile and in grid layouts. */
export default function ComponentCard({ component, onPredict }) {
  const safety = component.is_safety_critical ?? isSafetyCritical(component.component_type);

  return (
    <article className="card p-4 transition-shadow hover:shadow-elevated">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to={`/components/${component.component_id}`}
            className="font-mono text-sm font-bold text-navy-900 hover:text-accent"
          >
            {component.component_id}
          </Link>
          <p className="mt-0.5 flex items-center gap-1.5 text-sm text-steel-600">
            <Boxes className="h-3.5 w-3.5" aria-hidden="true" />
            {component.component_type}
            <span className="text-steel-300">|</span>
            {materialWithGrade(component.material, component.material_grade_label)}
          </p>
        </div>
        <HealthBadge score={component.health_score} size="sm" showBand={false} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <RecommendationBadge recommendation={component.recommendation} size="sm" />
        <StatusBadge status={component.current_status} size="sm" />
        {safety ? <SafetyChip compact /> : null}
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-steel-600">
        <div className="flex items-center gap-1.5">
          <Calendar className="h-3.5 w-3.5 text-steel-400" aria-hidden="true" />
          <span>{formatAge(component.component_age)}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <MapPin className="h-3.5 w-3.5 text-steel-400" aria-hidden="true" />
          <span className="truncate">{component.location || 'Unassigned'}</span>
        </div>
        <div className="col-span-2 text-steel-500">
          Last service: {formatDate(component.last_service_date)}
        </div>
      </dl>

      <div className="mt-4 flex flex-wrap gap-2">
        <Link to={`/passport/${component.component_id}`} className="btn-secondary btn-sm">
          <QrCode className="h-3.5 w-3.5" aria-hidden="true" />
          Passport
        </Link>
        <Link to={`/components/${component.component_id}`} className="btn-ghost btn-sm">
          Details
        </Link>
        {onPredict ? (
          <button type="button" className="btn-accent btn-sm" onClick={() => onPredict(component)}>
            Run AI assessment
          </button>
        ) : null}
      </div>
    </article>
  );
}

/** Dense key/value grid used on detail pages. */
export function SpecGrid({ items = [], columns = 2 }) {
  return (
    <dl
      className={`grid gap-x-6 gap-y-3 ${
        columns === 3 ? 'sm:grid-cols-3' : columns === 4 ? 'sm:grid-cols-4' : 'sm:grid-cols-2'
      }`}
    >
      {items.map((item) => (
        <div key={item.label} className="border-b border-steel-100 pb-2">
          <dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-steel-500">
            {item.label}
          </dt>
          <dd className="mt-0.5 text-sm font-medium text-navy-900">
            {item.value ?? '-'}
            {item.unit ? <span className="ml-1 text-xs text-steel-500">{item.unit}</span> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}
