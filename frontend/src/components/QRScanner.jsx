import { useEffect, useRef, useState } from 'react';
import { Camera, CameraOff, ImageUp, Keyboard, Search } from 'lucide-react';
import { passportApi } from '../api/client';
import ErrorMessage from './ErrorMessage';

const REGION_ID = 'kone-elevate-qr-region';

/**
 * Why the live camera could not start, in words a technician can act on.
 *
 * html5-qrcode rejects with plain strings as well as DOMExceptions, so the
 * browser's own error name is looked for in either.
 */
export function cameraErrorMessage(error) {
  const detail = String(error?.name ? `${error.name}: ${error.message}` : error ?? '');
  const fallback = 'Use "Scan from a photo" or the manual lookup below instead.';
  if (typeof window !== 'undefined' && window.isSecureContext === false) {
    return `The camera only works on a secure (https://) page, and this one was opened over http://. Open the https:// address instead, or ${fallback.charAt(0).toLowerCase()}${fallback.slice(1)}`;
  }
  if (typeof navigator !== 'undefined' && !navigator.mediaDevices?.getUserMedia) {
    return `This browser does not allow live camera access - often an in-app browser opened from a scanned link. Open the page in Chrome or Safari, or ${fallback.charAt(0).toLowerCase()}${fallback.slice(1)}`;
  }
  if (/NotAllowed|Permission/i.test(detail)) {
    return `Camera permission was denied. Allow the camera for this site in the browser's site settings and try again. ${fallback}`;
  }
  if (/NotFound|Overconstrained|DevicesNotFound/i.test(detail)) {
    return `No usable camera was found on this device. ${fallback}`;
  }
  if (/NotReadable|TrackStart|Could not start/i.test(detail)) {
    return `The camera is in use by another app. Close other camera apps and try again. ${fallback}`;
  }
  return `The camera could not start${detail ? ` (${detail})` : ''}. ${fallback}`;
}

/**
 * QR scanner with a guaranteed manual fallback.
 *
 * Camera access frequently fails in the field: no permission, no HTTPS, no
 * camera at all. The component therefore *always* renders the manual
 * component-id lookup, and the camera is strictly an enhancement on top.
 */
export default function QRScanner({ onResolved, autoStart = false }) {
  const [scanning, setScanning] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [manualValue, setManualValue] = useState('');
  const [lookupError, setLookupError] = useState(null);
  const [busy, setBusy] = useState(false);

  const scannerRef = useRef(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopCamera();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (autoStart) startCamera();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart]);

  async function resolveValue(value) {
    setBusy(true);
    setLookupError(null);
    try {
      const result = await passportApi.resolve(value);
      if (!result.found) {
        setLookupError({ message: result.message || `No component matches "${value}".` });
        return null;
      }
      onResolved?.(result.component_id, result);
      return result.component_id;
    } catch (error) {
      setLookupError(error);
      return null;
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  }

  async function startCamera() {
    setCameraError(null);
    try {
      // Loaded lazily so a browser without camera support never pays for it.
      const { Html5Qrcode } = await import('html5-qrcode');
      const scanner = new Html5Qrcode(REGION_ID, { verbose: false });
      scannerRef.current = scanner;

      await scanner.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 240, height: 240 } },
        async (decodedText) => {
          await stopCamera();
          await resolveValue(decodedText);
        },
        () => {
          /* per-frame decode misses are normal and intentionally ignored */
        },
      );
      if (mountedRef.current) setScanning(true);
    } catch (error) {
      if (mountedRef.current) {
        setCameraError({ message: cameraErrorMessage(error) });
        setScanning(false);
      }
      scannerRef.current = null;
    }
  }

  /** Decode a QR code from a photo - works where live camera access is blocked. */
  async function scanPhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    await stopCamera();
    setCameraError(null);
    try {
      const { Html5Qrcode } = await import('html5-qrcode');
      const decoded = await new Html5Qrcode(REGION_ID, { verbose: false }).scanFile(file, false);
      await resolveValue(decoded);
    } catch {
      setCameraError({
        message:
          'No QR code was found in that photo. Take it closer and straight on, with the whole code in frame and in focus.',
      });
    }
  }

  async function stopCamera() {
    const scanner = scannerRef.current;
    if (!scanner) return;
    try {
      await scanner.stop();
      await scanner.clear();
    } catch {
      // Already stopped - nothing to do.
    }
    scannerRef.current = null;
    if (mountedRef.current) setScanning(false);
  }

  const submitManual = async (event) => {
    event.preventDefault();
    const value = manualValue.trim();
    if (!value) return;
    await resolveValue(value);
  };

  return (
    <div className="space-y-4">
      {/* -------------------------------------------------------- camera */}
      <div className="card overflow-hidden">
        <div className="card-header">
          <div>
            <h3 className="card-title">Scan a component QR code</h3>
            <p className="mt-0.5 text-xs text-steel-500">
              Point the camera at the QR label on the component.
            </p>
          </div>
          {scanning ? (
            <button type="button" className="btn-secondary btn-sm" onClick={stopCamera}>
              <CameraOff className="h-3.5 w-3.5" aria-hidden="true" />
              Stop
            </button>
          ) : (
            <button type="button" className="btn-accent btn-sm" onClick={startCamera}>
              <Camera className="h-3.5 w-3.5" aria-hidden="true" />
              Start camera
            </button>
          )}
        </div>

        <div className="card-body">
          <div
            id={REGION_ID}
            className="mx-auto min-h-[220px] w-full max-w-sm overflow-hidden rounded-lg bg-navy-950/5"
          >
            {!scanning ? (
              <div className="flex min-h-[220px] flex-col items-center justify-center gap-2 text-steel-400">
                <Camera className="h-10 w-10" aria-hidden="true" />
                <p className="px-6 text-center text-xs">
                  Camera is off. Start it above, scan from a photo, or use the manual lookup.
                </p>
              </div>
            ) : null}
          </div>

          {/* The phone's own camera app takes the picture, so this works even
              where the browser blocks live camera access (http://, in-app browsers). */}
          <label className="btn-secondary btn-sm mx-auto mt-3 flex w-fit cursor-pointer">
            <ImageUp className="h-3.5 w-3.5" aria-hidden="true" />
            Scan from a photo
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              onChange={scanPhoto}
              disabled={busy}
            />
          </label>

          {cameraError ? (
            <ErrorMessage error={cameraError} compact className="mt-3" title="Camera unavailable" />
          ) : null}
        </div>
      </div>

      {/* -------------------------------------------------- manual lookup */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <Keyboard className="mr-1.5 inline h-4 w-4" aria-hidden="true" />
              Manual lookup
            </h3>
            <p className="mt-0.5 text-xs text-steel-500">
              Enter a component id, serial number, QR token or a full passport URL.
            </p>
          </div>
        </div>
        <form onSubmit={submitManual} className="card-body flex flex-col gap-3 sm:flex-row">
          <input
            className="input font-mono"
            placeholder="KE-MOT-000001"
            value={manualValue}
            onChange={(event) => setManualValue(event.target.value)}
            aria-label="Component identifier"
          />
          <button type="submit" className="btn-primary shrink-0" disabled={busy || !manualValue.trim()}>
            <Search className="h-4 w-4" aria-hidden="true" />
            {busy ? 'Looking up...' : 'Open passport'}
          </button>
        </form>
        {lookupError ? (
          <div className="px-5 pb-5">
            <ErrorMessage error={lookupError} compact />
          </div>
        ) : null}
      </div>
    </div>
  );
}
