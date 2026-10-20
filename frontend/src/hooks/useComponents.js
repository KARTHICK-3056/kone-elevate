/** Data hooks for the component registry. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { componentsApi, passportApi } from '../api/client';

/**
 * Paginated, filterable component list.
 *
 * Requests are keyed on a serialised parameter object and stale responses are
 * discarded, so rapid filter changes never render out-of-order data.
 */
export function useComponents(initialParams = {}) {
  const [params, setParams] = useState({
    page: 1,
    page_size: 25,
    sort_by: 'component_id',
    sort_dir: 'asc',
    ...initialParams,
  });
  const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 25, pages: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const requestId = useRef(0);

  const key = useMemo(() => JSON.stringify(params), [params]);

  const fetchPage = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const response = await componentsApi.list(JSON.parse(key));
      if (id === requestId.current) setData(response);
    } catch (err) {
      if (id === requestId.current) setError(err);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    fetchPage();
  }, [fetchPage]);

  const updateParams = useCallback((changes) => {
    setParams((previous) => {
      const next = { ...previous, ...changes };
      // Any change other than paging resets to the first page.
      if (!('page' in changes)) next.page = 1;
      return next;
    });
  }, []);

  const resetFilters = useCallback(() => {
    setParams({ page: 1, page_size: 25, sort_by: 'component_id', sort_dir: 'asc' });
  }, []);

  const toggleSort = useCallback((field) => {
    setParams((previous) => ({
      ...previous,
      sort_by: field,
      sort_dir: previous.sort_by === field && previous.sort_dir === 'asc' ? 'desc' : 'asc',
      page: 1,
    }));
  }, []);

  return { ...data, params, loading, error, updateParams, resetFilters, toggleSort, refresh: fetchPage };
}

/** A single component with its service history and assessment history. */
export function useComponent(componentId) {
  const [component, setComponent] = useState(null);
  const [events, setEvents] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!componentId) return;
    setLoading(true);
    setError(null);
    try {
      const [componentData, eventData, predictionData] = await Promise.all([
        componentsApi.get(componentId),
        componentsApi.serviceEvents(componentId),
        componentsApi.predictions(componentId),
      ]);
      setComponent(componentData);
      setEvents(eventData.items || []);
      setPredictions(predictionData.items || []);
    } catch (err) {
      setError(err);
      setComponent(null);
    } finally {
      setLoading(false);
    }
  }, [componentId]);

  useEffect(() => {
    load();
  }, [load]);

  return { component, events, predictions, loading, error, refresh: load };
}

/** The full digital passport payload for one component. */
export function usePassport(componentId) {
  const [passport, setPassport] = useState(null);
  const [loading, setLoading] = useState(Boolean(componentId));
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!componentId) {
      setPassport(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setPassport(await passportApi.get(componentId));
    } catch (err) {
      setError(err);
      setPassport(null);
    } finally {
      setLoading(false);
    }
  }, [componentId]);

  useEffect(() => {
    load();
  }, [load]);

  return { passport, loading, error, refresh: load };
}

/** Material profile and usage-adjusted life projection for one component. */
export function useLifeAssessment(componentId) {
  const [life, setLife] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!componentId) return;
    setError(null);
    try {
      setLife(await passportApi.life(componentId));
    } catch (err) {
      setError(err);
      setLife(null);
    }
  }, [componentId]);

  useEffect(() => {
    load();
  }, [load]);

  return { life, error, refresh: load };
}

/** Distinct filter values (locations, manufacturers) for the filter bar. */
export function useComponentFilters() {
  const [filters, setFilters] = useState({ locations: [], manufacturers: [] });

  useEffect(() => {
    let cancelled = false;
    componentsApi
      .filters()
      .then((data) => {
        if (!cancelled) setFilters(data);
      })
      .catch(() => {
        /* filter vocabulary is optional - the static constants still apply */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return filters;
}
