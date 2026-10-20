import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowDown,
  ArrowUp,
  Boxes,
  Download,
  Filter,
  Plus,
  QrCode,
  RotateCcw,
  Search,
} from 'lucide-react';
import { componentsApi } from '../api/client';
import { useComponentFilters, useComponents } from '../hooks/useComponents';
import HealthBadge, { RecommendationBadge, SafetyChip, StatusBadge } from '../components/HealthBadge';
import ErrorMessage, { EmptyState } from '../components/ErrorMessage';
import { TableSkeleton } from '../components/Loading';
import Modal from '../components/Modal';
import AddComponentForm from './partials/AddComponentForm';
import {
  COMPONENT_TYPES,
  LIFECYCLE_STATUSES,
  MATERIALS,
  PAGE_SIZE_OPTIONS,
  RECOMMENDATIONS,
} from '../utils/constants';
import {
  cx,
  downloadBlob,
  formatAge,
  formatDate,
  formatPercent,
  humanise,
  materialWithGrade,
} from '../utils/formatters';

import { useAuth } from '../context/AuthContext';

const COLUMNS = [
  { key: 'component_id', label: 'Component ID', sortable: true },
  { key: 'component_type', label: 'Type', sortable: true },
  { key: 'component_age', label: 'Age', sortable: false },
  { key: 'health_score', label: 'Health', sortable: true },
  { key: 'current_status', label: 'Status', sortable: true },
  { key: 'recommendation', label: 'Recommendation', sortable: false },
  { key: 'confidence', label: 'Confidence', sortable: false },
  { key: 'safety', label: 'Safety', sortable: false },
  { key: 'last_service', label: 'Last service', sortable: false },
  { key: 'actions', label: '', sortable: false },
];

/** Component registry: search, filter, sort, paginate, create and export. */
export default function Components() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useComponentFilters();
  const [showFilters, setShowFilters] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [searchInput, setSearchInput] = useState(searchParams.get('search') || '');
  const { user } = useAuth();
  // Branch users see their own frontline unit by default; the API's
  // all_units option widens that to the whole country (never beyond it).
  const homeUnit = user?.frontline_unit;

  const initialParams = useMemo(() => {
    const params = {};
    const recommendation = searchParams.get('recommendation');
    const type = searchParams.get('component_type');
    const status = searchParams.get('current_status');
    if (recommendation) params.recommendation = [recommendation];
    if (type) params.component_type = [type];
    if (status) params.current_status = [status];
    if (searchParams.get('search')) params.search = searchParams.get('search');
    if (searchParams.get('all_units') === 'true') params.all_units = true;
    return params;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const {
    items,
    total,
    page,
    page_size: pageSize,
    pages,
    params,
    loading,
    error,
    updateParams,
    resetFilters,
    toggleSort,
    refresh,
  } = useComponents(initialParams);

  // Debounced free-text search.
  useEffect(() => {
    const timer = setTimeout(() => {
      updateParams({ search: searchInput.trim() || undefined });
    }, 350);
    return () => clearTimeout(timer);
  }, [searchInput, updateParams]);

  const toggleMulti = (field, value) => {
    const current = params[field] || [];
    const next = current.includes(value)
      ? current.filter((entry) => entry !== value)
      : [...current, value];
    updateParams({ [field]: next.length ? next : undefined });
  };

  const exportCsv = async () => {
    try {
      const blob = await componentsApi.exportCsv();
      downloadBlob(blob, 'kone_elevate_components.csv');
    } catch {
      // The error banner below already covers API failures.
    }
  };

  const activeFilterCount = ['component_type', 'material', 'current_status', 'recommendation'].reduce(
    (count, field) => count + (params[field]?.length || 0),
    0,
  );

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-navy-900">Components</h1>
          <p className="mt-1 text-sm text-steel-500">
            {loading
              ? 'Loading...'
              : `${total.toLocaleString()} components ${
                  homeUnit && !params.all_units ? `in ${homeUnit}` : user?.country ? `in ${user.country}` : 'in the registry'
                }`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {homeUnit ? (
            <div className="inline-flex rounded-lg border border-steel-300 bg-white p-0.5" role="group" aria-label="Which components to show">
              {[
                { value: false, label: `My branch (${homeUnit})` },
                { value: true, label: `All units${user?.country ? ` in ${user.country}` : ''}` },
              ].map((option) => (
                <button
                  key={String(option.value)}
                  type="button"
                  aria-pressed={Boolean(params.all_units) === option.value}
                  onClick={() => updateParams({ all_units: option.value || undefined })}
                  className={cx(
                    'rounded-md px-3 py-1.5 text-xs font-semibold',
                    Boolean(params.all_units) === option.value
                      ? 'bg-navy-800 text-white'
                      : 'text-steel-600 hover:bg-steel-100',
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}
          <Link to="/passport" className="btn-secondary" title="Scan QR code or lookup passport">
            <QrCode className="h-4 w-4" aria-hidden="true" />
            Scan QR
          </Link>
          <button type="button" onClick={exportCsv} className="btn-secondary">
            <Download className="h-4 w-4" aria-hidden="true" />
            Export CSV
          </button>
          <button type="button" onClick={() => setShowAdd(true)} className="btn-accent">
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add component
          </button>
        </div>
      </header>

      {/* ---------------------------------------------------- search bar */}
      <div className="card p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-400"
              aria-hidden="true"
            />
            <input
              className="input pl-9"
              placeholder="Search by component id, serial number, manufacturer or origin"
              value={searchInput}
              onChange={(event) => {
                setSearchInput(event.target.value);
                setSearchParams(event.target.value ? { search: event.target.value } : {});
              }}
              aria-label="Search components"
            />
          </div>

          <button
            type="button"
            onClick={() => setShowFilters((value) => !value)}
            className={cx('btn-secondary', activeFilterCount && 'ring-2 ring-accent')}
          >
            <Filter className="h-4 w-4" aria-hidden="true" />
            Filters
            {activeFilterCount ? (
              <span className="ml-1 rounded-full bg-accent px-1.5 text-[0.65rem] text-white">
                {activeFilterCount}
              </span>
            ) : null}
          </button>

          <select
            className="select w-auto"
            value={pageSize}
            onChange={(event) => updateParams({ page_size: Number(event.target.value), page: 1 })}
            aria-label="Rows per page"
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option} / page
              </option>
            ))}
          </select>
        </div>

        {showFilters ? (
          <div className="mt-4 grid gap-4 border-t border-steel-200 pt-4 sm:grid-cols-2 lg:grid-cols-4">
            <FilterGroup
              label="Component type"
              options={COMPONENT_TYPES}
              selected={params.component_type || []}
              onToggle={(value) => toggleMulti('component_type', value)}
            />
            <FilterGroup
              label="Material"
              options={MATERIALS}
              selected={params.material || []}
              onToggle={(value) => toggleMulti('material', value)}
            />
            <FilterGroup
              label="Lifecycle status"
              options={LIFECYCLE_STATUSES}
              selected={params.current_status || []}
              onToggle={(value) => toggleMulti('current_status', value)}
              humanised
            />
            <div className="space-y-3">
              <FilterGroup
                label="AI recommendation"
                options={RECOMMENDATIONS}
                selected={params.recommendation || []}
                onToggle={(value) => toggleMulti('recommendation', value)}
              />
              <div>
                <label className="label" htmlFor="location-filter">
                  Location
                </label>
                <select
                  id="location-filter"
                  className="select"
                  value={params.location || ''}
                  onChange={(event) => updateParams({ location: event.target.value || undefined })}
                >
                  <option value="">All locations</option>
                  {filters.locations.map((location) => (
                    <option key={location} value={location}>
                      {location}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={() => {
                  resetFilters();
                  setSearchInput('');
                  setSearchParams({});
                }}
                className="btn-ghost btn-sm"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                Reset all filters
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {/* -------------------------------------------------------- results */}
      {error ? <ErrorMessage error={error} onRetry={refresh} /> : null}

      <div className="card overflow-hidden">
        {loading ? (
          <TableSkeleton rows={8} columns={7} />
        ) : items.length === 0 ? (
          <EmptyState
            title="No components match these filters"
            description="Try clearing the search box or resetting the filters. If the registry is empty, run the seed script in backend/."
            icon={Boxes}
            action={
              <button
                type="button"
                onClick={() => {
                  resetFilters();
                  setSearchInput('');
                }}
                className="btn-secondary"
              >
                Reset filters
              </button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  {COLUMNS.map((column) => (
                    <th key={column.key}>
                      {column.sortable ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(column.key)}
                          className="inline-flex items-center gap-1 hover:text-navy-900"
                        >
                          {column.label}
                          {params.sort_by === column.key ? (
                            params.sort_dir === 'asc' ? (
                              <ArrowUp className="h-3 w-3" aria-hidden="true" />
                            ) : (
                              <ArrowDown className="h-3 w-3" aria-hidden="true" />
                            )
                          ) : null}
                        </button>
                      ) : (
                        column.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((component) => (
                  <tr key={component.component_id}>
                    <td>
                      <Link
                        to={`/components/${component.component_id}`}
                        className="font-mono text-xs font-semibold text-navy-900 hover:text-accent"
                      >
                        {component.component_id}
                      </Link>
                      <span className="block text-[0.65rem] text-steel-400">
                        {component.serial_number}
                      </span>
                    </td>
                    <td>
                      <span className="text-sm">{component.component_type}</span>
                      <span className="block text-[0.65rem] text-steel-400">
                        {materialWithGrade(component.material, component.material_grade_label)}
                      </span>
                    </td>
                    <td className="whitespace-nowrap text-sm">{formatAge(component.component_age)}</td>
                    <td>
                      <HealthBadge score={component.health_score} size="sm" showBand={false} />
                    </td>
                    <td>
                      <StatusBadge status={component.current_status} size="sm" />
                    </td>
                    <td>
                      <RecommendationBadge recommendation={component.recommendation} size="sm" />
                    </td>
                    <td className="whitespace-nowrap font-mono text-xs">
                      {component.confidence ? formatPercent(component.confidence, 1) : '-'}
                    </td>
                    <td>{component.is_safety_critical ? <SafetyChip compact /> : null}</td>
                    <td className="whitespace-nowrap text-xs text-steel-500">
                      {formatDate(component.last_service_date)}
                    </td>
                    <td>
                      <div className="flex justify-end gap-1">
                        <Link
                          to={`/passport/${component.component_id}`}
                          className="btn-ghost btn-sm"
                          title="Open digital passport"
                        >
                          <QrCode className="h-3.5 w-3.5" aria-hidden="true" />
                        </Link>
                        <Link to={`/components/${component.component_id}`} className="btn-ghost btn-sm">
                          Details
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ---------------------------------------------------- pagination */}
        {!loading && items.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-steel-200 px-4 py-3">
            <p className="text-xs text-steel-500">
              Showing {(page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} of{' '}
              {total.toLocaleString()}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={page <= 1}
                onClick={() => updateParams({ page: page - 1 })}
              >
                Previous
              </button>
              <span className="text-xs font-medium text-steel-600">
                Page {page} of {pages || 1}
              </span>
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={page >= pages}
                onClick={() => updateParams({ page: page + 1 })}
              >
                Next
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <Modal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        title="Register a component"
        description="Creates the component, allocates a QR passport token, writes an audit record and runs an initial AI assessment."
        size="lg"
      >
        <AddComponentForm
          onCreated={() => {
            setShowAdd(false);
            refresh();
          }}
          onCancel={() => setShowAdd(false)}
        />
      </Modal>
    </div>
  );
}

/** Checkbox group used inside the filter panel. */
function FilterGroup({ label, options, selected, onToggle, humanised = false }) {
  return (
    <fieldset>
      <legend className="label">{label}</legend>
      <div className="max-h-40 space-y-1 overflow-y-auto pr-1">
        {options.map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm text-steel-700">
            <input
              type="checkbox"
              className="h-3.5 w-3.5 rounded border-steel-300 text-accent focus:ring-accent"
              checked={selected.includes(option)}
              onChange={() => onToggle(option)}
            />
            {humanised ? humanise(option) : option}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
