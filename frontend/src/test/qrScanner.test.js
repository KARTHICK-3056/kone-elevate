import { afterEach, describe, expect, it, vi } from 'vitest';
import { cameraErrorMessage } from '../components/QRScanner';

describe('cameraErrorMessage', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('explains that an http:// page cannot use the camera', () => {
    vi.stubGlobal('isSecureContext', false);
    expect(cameraErrorMessage('anything')).toMatch(/secure \(https:\/\/\) page/);
  });

  it('points an in-app browser at Chrome or Safari', () => {
    vi.stubGlobal('isSecureContext', true);
    vi.stubGlobal('navigator', { mediaDevices: undefined });
    expect(cameraErrorMessage('anything')).toMatch(/Chrome or Safari/);
  });

  it('reads the error name out of the plain strings html5-qrcode rejects with', () => {
    vi.stubGlobal('isSecureContext', true);
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: () => {} } });
    expect(cameraErrorMessage('Error getting userMedia, error = NotAllowedError: Permission denied')).toMatch(
      /permission was denied/,
    );
    expect(cameraErrorMessage({ name: 'NotReadableError', message: 'Could not start video source' })).toMatch(
      /in use by another app/,
    );
    expect(cameraErrorMessage('Something odd')).toMatch(/could not start \(Something odd\)/);
  });
});
