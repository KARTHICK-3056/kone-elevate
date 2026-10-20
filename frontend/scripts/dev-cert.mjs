/**
 * Self-signed HTTPS certificate for opening the dev server on a phone.
 *
 * Phone browsers only allow the camera (the in-app QR scanner) on HTTPS, so
 * `npm run dev:phone` serves the app over HTTPS on the local network. This
 * script (re)creates `.certs/dev-key.pem` and `.certs/dev-cert.pem` covering
 * localhost and every current IPv4 address of this machine - rerun it after
 * joining a different network, which happens automatically via dev:phone.
 *
 * Needs `openssl`: on Windows it ships with Git for Windows.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { networkInterfaces, tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const certDir = join(root, '.certs');
const keyPath = join(certDir, 'dev-key.pem');
const certPath = join(certDir, 'dev-cert.pem');
const sansPath = join(certDir, 'sans.txt');
export const PHONE_PORT = 5174;

function lanAddresses() {
  return Object.values(networkInterfaces())
    .flat()
    .filter((net) => net && net.family === 'IPv4' && !net.internal && !net.address.startsWith('169.254.'))
    .map((net) => net.address);
}

function findOpenssl() {
  const candidates = [
    'openssl',
    'C:\\Program Files\\Git\\usr\\bin\\openssl.exe',
    'C:\\Program Files\\Git\\mingw64\\bin\\openssl.exe',
  ];
  for (const candidate of candidates) {
    try {
      execFileSync(candidate, ['version'], { stdio: 'ignore' });
      return candidate;
    } catch {
      // try the next one
    }
  }
  throw new Error('openssl was not found. Install Git for Windows (it includes openssl) and try again.');
}

const addresses = lanAddresses();
const sans = ['DNS:localhost', 'IP:127.0.0.1', ...addresses.map((ip) => `IP:${ip}`)].join(',');
const current = existsSync(sansPath) ? readFileSync(sansPath, 'utf8') : '';

if (current !== sans || !existsSync(keyPath) || !existsSync(certPath)) {
  mkdirSync(certDir, { recursive: true });
  const config = join(tmpdir(), `kone-elevate-dev-cert-${process.pid}.cnf`);
  writeFileSync(
    config,
    [
      '[req]',
      'distinguished_name = dn',
      'x509_extensions = ext',
      'prompt = no',
      '[dn]',
      'CN = KONE ELEVATE dev',
      '[ext]',
      `subjectAltName = ${sans}`,
      'basicConstraints = CA:FALSE',
      'keyUsage = digitalSignature, keyEncipherment',
      'extendedKeyUsage = serverAuth',
      '',
    ].join('\n'),
  );
  execFileSync(
    findOpenssl(),
    ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '365', '-keyout', keyPath, '-out', certPath, '-config', config],
    { stdio: 'ignore' },
  );
  writeFileSync(sansPath, sans);
  console.log('Created a self-signed certificate for:', sans.replace(/DNS:|IP:/g, ''));
}

console.log('\nOpen the app on a phone on the same network:');
for (const ip of addresses) console.log(`  https://${ip}:${PHONE_PORT}`);
console.log('The phone warns that the certificate is not trusted - choose Advanced > Proceed.\n');
