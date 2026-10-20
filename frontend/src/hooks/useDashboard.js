/** Hooks for the dashboard, analytics and audit pages. */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { auditApi, dashboardApi } from '../api/client';

/**
 * Dashboard payload.
 *
 * All series are fetched in parallel; a single failing chart never blocks the
 * headline figures, so the command centre degrades gracefully.
 */
export function useDashboard() {
  const [data, setData] = useState({
    summary: null,
    disposition: null,
    health: null,
    componentTypes: null,
    lifecycle: null,
    confidence: null,
    activity: null,
    recoveryValue: [],
    impact: null,
    safetyQueue: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The summary is required; if it fails the page shows an error state.
      const summary = await dashboardApi.summary();

      const [
        disposition,
        health,
        componentTypes,
        lifecycle,
        confidence,
        activity,
        recoveryValue,
        impact,
        safetyQueue,
      ] = await Promise.all([
        dashboardApi.disposition().catch(() => null),
        dashboardApi.healthDistribution().catch(() => null),
        dashboardApi.componentTypes().catch(() => null),
        dashboardApi.lifecycle().catch(() => null),
        dashboardApi.confidence().catch(() => null),
        dashboardApi.monthlyActivity().catch(() => null),
        dashboardApi.recoveryValue().catch(() => []),
        dashboardApi.impact().catch(() => null),
        dashboardApi.safetyQueue(10).catch(() => []),
      ]);

      setData({
        summary,
        disposition,
        health,
        componentTypes,
        lifecycle,
        confidence,
        activity,
        recoveryValue,
        impact,
        safetyQueue,
      });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /** Items surfaced in the navbar notification tray. */
  const notifications = useMemo(() => {
    const notes = [];
    if (data.summary?.components_awaiting_inspection) {
      notes.push({
        id: 'inspection',
        title: `${data.summary.components_awaiting_inspection} components awaiting inspection`,
        description: 'Safety-critical components need human sign-off before any disposition.',
      });
    }
    if (data.summary?.disposal) {
      notes.push({
        id: 'disposal',
        title: `${data.summary.disposal} components recommended for disposal`,
        description: 'Review before scrapping - a second assessment may change the outcome.',
      });
    }
    return notes;
  }, [data.summary]);

  return { ...data, notifications, loading, error, refresh: load };
}

/** Analytics page payload (single round trip, filterable). */
export function useAnalytics(initialFilters = {}) {
  const [filters, setFilters] = useState(initialFilters);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const key = useMemo(() => JSON.stringify(filters), [filters]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAnalytics(await dashboardApi.analytics(JSON.parse(key)));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    load();
  }, [load]);

  return { analytics, filters, setFilters, loading, error, refresh: load };
}

/** Audit chain page payload. */
export function useAuditLog(initialParams = {}) {
  const [params, setParams] = useState({ page: 1, page_size: 25, ...initialParams });
  const [page, setPage] = useState({ items: [], total: 0, page: 1, page_size: 25, pages: 0 });
  const [stats, setStats] = useState(null);
  const [verification, setVerification] = useState(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState(null);

  const key = useMemo(() => JSON.stringify(params), [params]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pageData, statsData] = await Promise.all([
        auditApi.list(JSON.parse(key)),
        auditApi.stats().catch(() => null),
      ]);
      setPage(pageData);
      setStats(statsData);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    load();
  }, [load]);

  const verify = useCallback(async () => {
    setVerifying(true);
    try {
      const result = await auditApi.verify();
      setVerification(result);
      return result;
    } catch (err) {
      setError(err);
      return null;
    } finally {
      setVerifying(false);
    }
  }, []);

  return {
    ...page,
    params,
    setParams,
    stats,
    verification,
    verify,
    verifying,
    loading,
    error,
    refresh: load,
  };
}
