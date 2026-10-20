import { useState } from 'react';
import { Copy, Check, Download, Printer, QrCode } from 'lucide-react';
import { passportApi } from '../api/client';
import { cx } from '../utils/formatters';

/**
 * Passport QR code panel.
 *
 * Prefers the inline data URI supplied by the passport endpoint (one fewer
 * request, and it survives printing); falls back to the streaming PNG endpoint.
 */
export default function QRCodeDisplay({
  componentId,
  dataUri,
  passportUrl,
  size = 190,
  showActions = true,
  className = '',
}) {
  const [copied, setCopied] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);

  const source = dataUri || passportApi.qrImageUrl(componentId);
  const url = passportUrl || `${window.location.origin}/passport/${componentId}`;

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be blocked; the URL stays visible below regardless.
      setCopied(false);
    }
  };

  return (
    <div className={cx('flex flex-col items-center gap-3', className)}>
      <div className="rounded-xl border-2 border-navy-900 bg-white p-3">
        {imageFailed ? (
          <div
            className="flex flex-col items-center justify-center gap-2 text-steel-400"
            style={{ width: size, height: size }}
          >
            <QrCode className="h-10 w-10" aria-hidden="true" />
            <p className="px-2 text-center text-xs">QR image unavailable</p>
          </div>
        ) : (
          <img
            src={source}
            alt={`Passport QR code for component ${componentId}`}
            width={size}
            height={size}
            style={{ width: size, height: size }}
            onError={() => setImageFailed(true)}
          />
        )}
      </div>

      <div className="text-center">
        <p className="font-mono text-sm font-bold text-navy-900">{componentId}</p>
        <p className="mt-0.5 max-w-[16rem] break-all text-[0.65rem] text-steel-500">{url}</p>
      </div>

      {showActions ? (
        <div className="no-print flex flex-wrap justify-center gap-2">
          <button type="button" onClick={copyLink} className="btn-secondary btn-sm">
            {copied ? (
              <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
            ) : (
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {copied ? 'Copied' : 'Copy link'}
          </button>
          <a
            href={passportApi.qrDownloadUrl(componentId)}
            className="btn-secondary btn-sm"
            download
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            PNG
          </a>
          <button type="button" onClick={() => window.print()} className="btn-secondary btn-sm">
            <Printer className="h-3.5 w-3.5" aria-hidden="true" />
            Print
          </button>
        </div>
      ) : null}
    </div>
  );
}
