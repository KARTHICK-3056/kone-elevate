import { existsSync, readFileSync } from 'node:fs';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// `npm run dev:phone` (mode "phone") serves HTTPS on the local network so a
// phone can open the app and use its camera for the QR scanner - browsers
// allow the camera only on HTTPS. The certificate comes from
// scripts/dev-cert.mjs; plain `npm run dev` is unchanged.
const phoneHttps = (mode) => {
  const key = new URL('./.certs/dev-key.pem', import.meta.url);
  const cert = new URL('./.certs/dev-cert.pem', import.meta.url);
  if (mode !== 'phone' || !existsSync(key) || !existsSync(cert)) return undefined;
  return { key: readFileSync(key), cert: readFileSync(cert) };
};

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    VitePWA({
      // P5: a technician scans a passport in a basement machine room with no
      // signal. `registerType: 'autoUpdate'` means a deployed update is
      // picked up on the next online visit without the app ever nagging
      // someone with no connectivity to reload.
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'KONE ELEVATE - Component Passport',
        short_name: 'KE Passport',
        description:
          'AI-powered circular-economy platform for elevator component lifecycle management. Prototype.',
        theme_color: '#0f1c33',
        background_color: '#0f1c33',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/pwa-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // The app shell (JS/CSS/HTML) is precached so the app *opens* with
        // no network at all - a technician's phone in a machine room needs
        // the UI to load before offline data even matters.
        globPatterns: ['**/*.{js,css,html,svg,png,ico}'],
        runtimeCaching: [
          {
            // Passport lookups: what a technician actually re-opens offline.
            // NetworkFirst - always prefer a live answer, fall back to the
            // last-seen copy only when the network genuinely is not there.
            urlPattern: ({ url, sameOrigin }) =>
              sameOrigin && /\/api\/v1\/passports\//.test(url.pathname) && !/\/qr/.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'ke-passport-cache',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // The component registry list/detail views, same reasoning.
            urlPattern: ({ url, sameOrigin }) =>
              sameOrigin && /\/api\/v1\/components(\/|\?|$)/.test(url.pathname + url.search),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'ke-component-cache',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 500, maxAgeSeconds: 60 * 60 * 24 * 7 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // QR code images: rendered once, reused often, cheap to cache.
            urlPattern: ({ url, sameOrigin }) => sameOrigin && /\/api\/v1\/passports\/.*\/qr/.test(url.pathname),
            handler: 'CacheFirst',
            options: {
              cacheName: 'ke-qr-cache',
              expiration: { maxEntries: 300, maxAgeSeconds: 60 * 60 * 24 * 90 },
            },
          },
        ],
        // Mutating requests (POST/PUT/DELETE) are handled by our own
        // IndexedDB outbox (src/offline/*), not Workbox's background-sync
        // recipe - see docs/offline-pwa.md for why: this system's writes
        // need domain-aware conflict handling (a duplicate serial number,
        // an already-matched recovery item) that a generic replay queue
        // cannot make sense of on its own.
        navigateFallback: '/index.html',
      },
      devOptions: {
        // Lets `npm run dev` exercise the service worker too, not just a
        // production build - offline behaviour is otherwise easy to change
        // without ever noticing during normal development.
        enabled: true,
        type: 'module',
      },
    }),
  ],
  server: {
    host: true,
    port: mode === 'phone' ? 5174 : 5173,
    https: phoneHttps(mode),
    // Proxy keeps the dev experience working even when VITE_API_URL is unset.
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: true,
    port: 4173,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
    testTimeout: 15000,
  },
}));
