import { useCallback, useEffect, useRef, useState } from 'react';
import { simulationApi } from '../api/client';

/** Real-time interval between simulation steps while playing. */
const TICK_MS = 900;
/** Months kept in the on-page chart (the server keeps no history). */
const MAX_SERIES = 60 * 12;

export const SPEEDS = [
  { months: 1, label: '1 month / step' },
  { months: 3, label: '3 months / step' },
  { months: 6, label: '6 months / step' },
  { months: 12, label: '1 year / step' },
];

/**
 * Client side of the stateless simulation API.
 *
 * The server holds nothing between calls: the state it returns is kept here
 * and sent back with the next step. The user's load is read at every step,
 * so changing it mid-run takes effect from the next simulated month.
 */
export function useSimulation(initialLoad, initialComponent = null) {
  const [reference, setReference] = useState(null);
  const [load, setLoad] = useState(initialLoad);
  const [speed, setSpeed] = useState(3);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [series, setSeries] = useState([]);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const stateRef = useRef(null);
  const loadRef = useRef(initialLoad);
  const busyRef = useRef(false);
  const runningRef = useRef(false);
  const maxYearsRef = useRef(60);
  // Only the first load reads the URL; later starts are explicit calls.
  const initialComponentRef = useRef(initialComponent);

  loadRef.current = load;

  const step = useCallback(async (months) => {
    if (busyRef.current) return false;
    busyRef.current = true;
    setBusy(true);
    try {
      const response = await simulationApi.advance(stateRef.current, loadRef.current, months);
      stateRef.current = response.state;
      setResults(response.results);
      setSeries((previous) => [...previous, ...response.series].slice(-MAX_SERIES));
      setEvents(response.state.events || []);
      setError(null);
      if (response.results.years >= maxYearsRef.current - months / 12) {
        runningRef.current = false;
        setRunning(false);
      }
      return true;
    } catch (err) {
      setError(err);
      runningRef.current = false;
      setRunning(false);
      return false;
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, []);

  /** Seed the simulation from a real component's record. */
  const startFrom = useCallback(async (componentId) => {
    runningRef.current = false;
    setRunning(false);
    busyRef.current = true;
    setBusy(true);
    try {
      const response = await simulationApi.startFrom(componentId);
      stateRef.current = response.state;
      setResults(response.results);
      setSeries(response.series);
      setEvents(response.state.events || []);
      setLoad(response.results.focus.historical_load_kg);
      setError(null);
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, []);

  /** Save the current run to the focus component's passport (simulated, labelled). */
  const saveScenario = useCallback(async (name) => {
    const focus = stateRef.current?.focus;
    if (!focus) throw new Error('Only a simulation started from a real component can be saved.');
    return simulationApi.saveScenario(focus.component_id, stateRef.current, name || undefined);
  }, []);

  const reset = useCallback(async () => {
    runningRef.current = false;
    setRunning(false);
    stateRef.current = null;
    setSeries([]);
    setEvents([]);
    setResults(null);
    await step(1);
  }, [step]);

  // First load: calibration reference, then a brand-new lift.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await simulationApi.reference();
        if (cancelled) return;
        setReference(data);
        maxYearsRef.current = data.max_years;
        // KONE API first: the default load is the KONE movement loadPercentage
        // x rated load, unless the run starts from a real component's record.
        const koneLoad = data.reference?.traffic?.reference_load_kg?.value;
        if (koneLoad && !initialComponentRef.current) {
          loadRef.current = koneLoad;
          setLoad(koneLoad);
        }
      } catch (err) {
        if (!cancelled) setError(err);
      }
      if (cancelled) return;
      if (initialComponentRef.current) {
        const ok = await startFrom(initialComponentRef.current);
        if (ok || cancelled) return;
      }
      await step(1);
    })();
    return () => {
      cancelled = true;
    };
  }, [step, startFrom]);

  // Play loop: one step, wait, next - never two requests in flight.
  useEffect(() => {
    runningRef.current = running;
    if (!running) return undefined;
    let timer;
    const loop = async () => {
      if (!runningRef.current) return;
      const started = Date.now();
      const ok = await step(speed);
      if (!ok || !runningRef.current) return;
      timer = setTimeout(loop, Math.max(0, TICK_MS - (Date.now() - started)));
    };
    loop();
    return () => clearTimeout(timer);
  }, [running, speed, step]);

  return {
    reference,
    load,
    setLoad,
    speed,
    setSpeed,
    running,
    setRunning,
    results,
    series,
    events,
    error,
    busy,
    step,
    reset,
    startFrom,
    saveScenario,
  };
}
