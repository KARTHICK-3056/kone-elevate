/** Hooks around the AI assessment endpoints. */

import { useCallback, useEffect, useState } from 'react';
import { componentsApi, predictionApi } from '../api/client';

/**
 * Run an assessment, either against a stored component or a raw payload.
 *
 * The hook keeps the last successful result so the UI can keep showing it
 * while a new assessment runs.
 */
export function usePrediction() {
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const predictPayload = useCallback(async (payload) => {
    setLoading(true);
    setError(null);
    try {
      const result = await predictionApi.predict(payload);
      setPrediction(result);
      return result;
    } catch (err) {
      setError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const predictComponent = useCallback(async (componentId) => {
    setLoading(true);
    setError(null);
    try {
      const result = await componentsApi.predict(componentId);
      setPrediction(result);
      return result;
    } catch (err) {
      setError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setPrediction(null);
    setError(null);
  }, []);

  return { prediction, loading, error, predictPayload, predictComponent, reset };
}

/** Metadata and evaluation metrics for the deployed model. */
export function useModelInfo() {
  const [info, setInfo] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [importance, setImportance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const infoData = await predictionApi.modelInfo();
      setInfo(infoData);

      if (infoData.model_available) {
        const [metricsData, importanceData] = await Promise.all([
          predictionApi.modelMetrics().catch(() => null),
          predictionApi.featureImportance().catch(() => ({ gini: [], permutation: [], shap: [] })),
        ]);
        setMetrics(metricsData);
        setImportance(importanceData);
      } else {
        setMetrics(null);
        setImportance(null);
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { info, metrics, importance, loading, error, refresh: load };
}

/** Calibration reliability diagram, conformal and abstention statistics. */
export function useCalibration() {
  const [calibration, setCalibration] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await predictionApi.calibration();
      setCalibration(data);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { calibration, loading, error, refresh: load };
}

/** Most recent assessments across the whole fleet. */
export function useRecentPredictions(limit = 8) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    predictionApi
      .recent(limit)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [limit]);

  return { items, loading };
}
