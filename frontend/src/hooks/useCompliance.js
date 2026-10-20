/** Hooks around the regulatory disclosure endpoints (ESRS E5, BRSR, ledger). */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { complianceApi } from '../api/client';

/** Default to the current calendar year - the period a controller reports on. */
export function currentPeriod() {
  return String(new Date().getFullYear());
}

/**
 * Build the period options a user can pick: the current year, its four
 * quarters, and the two preceding years.
 */
export function periodOptions(reference = new Date()) {
  const year = reference.getFullYear();
  const options = [{ value: String(year), label: `${year} (full year)` }];
  for (let quarter = 1; quarter <= 4; quarter += 1) {
    options.push({ value: `${year}-Q${quarter}`, label: `${year} Q${quarter}` });
  }
  options.push({ value: String(year - 1), label: `${year - 1} (full year)` });
  options.push({ value: String(year - 2), label: `${year - 2} (full year)` });
  return options;
}

/**
 * Loads the E5 and BRSR disclosures for one period alongside ledger coverage.
 *
 * The three are fetched together because they must describe the same period:
 * rendering an E5 table for Q1 next to a BRSR table for the full year would
 * invite exactly the kind of mismatch a reporting controller must never
 * publish.
 */
export function useCompliance(initialPeriod = currentPeriod()) {
  const [period, setPeriod] = useState(initialPeriod);
  const [esrs, setEsrs] = useState(null);
  const [brsr, setBrsr] = useState(null);
  const [ledger, setLedger] = useState(null);
  const [anchors, setAnchors] = useState(null);
  const [circularity, setCircularity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [esrsData, brsrData, ledgerData, anchorData, circularityData] = await Promise.all([
        complianceApi.esrsE5(period),
        complianceApi.brsr(period),
        complianceApi.ledgerSummary(),
        complianceApi.anchors(),
        complianceApi.circularity(),
      ]);
      setEsrs(esrsData);
      setBrsr(brsrData);
      setLedger(ledgerData);
      setAnchors(anchorData);
      setCircularity(circularityData);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    load();
  }, [load]);

  const options = useMemo(() => periodOptions(), []);

  return {
    period,
    setPeriod,
    options,
    esrs,
    brsr,
    ledger,
    anchors,
    circularity,
    loading,
    error,
    refresh: load,
  };
}
