/** Hooks around the end-of-life forecast and capacity-planning endpoints. */

import { useCallback, useEffect, useState } from 'react';
import { forecastApi } from '../api/client';

/**
 * Loads the EOL forecast, capacity plan and site impact together.
 *
 * They share a horizon, so fetching them as one unit keeps the page from
 * rendering a capacity plan for 24 months next to a forecast for 12.
 */
export function useForecast(initialHorizon = 24, initialGroupBy = 'type') {
  const [horizon, setHorizon] = useState(initialHorizon);
  const [groupBy, setGroupBy] = useState(initialGroupBy);
  const [eol, setEol] = useState(null);
  const [capacity, setCapacity] = useState(null);
  const [siteImpact, setSiteImpact] = useState(null);
  const [model, setModel] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const info = await forecastApi.model();
      setModel(info);

      if (!info.forecast_available) {
        setEol(null);
        setCapacity(null);
        setSiteImpact(null);
        return;
      }

      const [eolData, capacityData, siteImpactData] = await Promise.all([
        forecastApi.eol({ horizon, group_by: groupBy }),
        forecastApi.capacity({ horizon }),
        forecastApi.siteImpact({ horizon: 3 }),
      ]);
      setEol(eolData);
      setCapacity(capacityData);
      setSiteImpact(siteImpactData);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [horizon, groupBy]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    eol,
    capacity,
    siteImpact,
    model,
    horizon,
    setHorizon,
    groupBy,
    setGroupBy,
    loading,
    error,
    refresh: load,
  };
}
