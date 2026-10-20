import { Loader2 } from 'lucide-react';
import { cx } from '../utils/formatters';

/** Inline spinner with an optional label. */
export function Spinner({ className = 'h-5 w-5', label }) {
  return (
    <span className="inline-flex items-center gap-2 text-steel-500" role="status" aria-live="polite">
      <Loader2 className={cx(className, 'animate-spin')} aria-hidden="true" />
      {label ? <span className="text-sm">{label}</span> : <span className="sr-only">Loading</span>}
    </span>
  );
}

/** Full-panel loading state used while a page fetches its data. */
export default function Loading({ label = 'Loading...', className = '' }) {
  return (
    <div className={cx('flex min-h-[220px] w-full items-center justify-center', className)}>
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-accent" aria-hidden="true" />
        <p className="text-sm font-medium text-steel-500">{label}</p>
      </div>
    </div>
  );
}

/** Skeleton block used for table and card placeholders. */
export function Skeleton({ className = 'h-4 w-full' }) {
  return <div className={cx('skeleton', className)} aria-hidden="true" />;
}

/** A skeleton grid matching the dashboard stat tiles. */
export function StatSkeleton({ count = 4 }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="card p-5">
          <Skeleton className="mb-3 h-3 w-24" />
          <Skeleton className="mb-2 h-8 w-32" />
          <Skeleton className="h-3 w-20" />
        </div>
      ))}
    </div>
  );
}

/** A skeleton table body. */
export function TableSkeleton({ rows = 6, columns = 6 }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-3">
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <Skeleton key={columnIndex} className="h-6 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}
