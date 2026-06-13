import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // PWA install icons are bake-time and follow the default theme (Veil).
      // Runtime favicon/apple-touch swapping per theme happens in
      // client/src/lib/themeIcons.ts.
      includeAssets: ['favicon.ico', 'icons/veil/icon-180.png'],
      manifest: {
        name: 'NEXUS',
        short_name: 'NEXUS',
        description: 'NEXUS - Narrative exploration and analysis',
        theme_color: '#09101c',
        background_color: '#09101c',
        display: 'standalone',
        orientation: 'any',
        icons: [
          {
            src: '/icons/veil/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any maskable'
          },
          {
            src: '/icons/veil/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable'
          },
          {
            src: '/icons/veil/icon-180.png',
            sizes: '180x180',
            type: 'image/png',
            purpose: 'any maskable'
          }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        globIgnores: [
          '**/character_portraits/**',
          // Non-default theme icons are fetched on demand at theme switch and
          // cached by the NetworkFirst runtimeCaching rule below — keep them
          // out of the install-time precache.
          '**/icons/gilded/**',
          '**/icons/vector/**',
        ],
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-cache',
              expiration: {
                maxEntries: 10,
                maxAgeSeconds: 60 * 60 * 24 * 365 // 1 year
              },
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          },
          {
            // Network-first strategy for PWA icons to support cache-busting
            urlPattern: /\/icons\/.*\.png$/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'pwa-icons-cache',
              networkTimeoutSeconds: 3,
              expiration: {
                maxEntries: 20,
                maxAgeSeconds: 60 * 60 * 24 * 7 // 1 week
              },
              cacheableResponse: {
                statuses: [0, 200]
              }
            }
          }
        ]
      }
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "client", "src"),
      "@shared": path.resolve(import.meta.dirname, "shared"),
      // "@assets": path.resolve(import.meta.dirname, "attached_assets"), // Removed - directory purged
    },
  },
  root: path.resolve(import.meta.dirname, "client"),
  optimizeDeps: {
    include: ['use-stick-to-bottom', 'harden-react-markdown'],
  },
  build: {
    outDir: path.resolve(import.meta.dirname, "dist/public"),
    emptyOutDir: true,
  },
  server: {
    host: '0.0.0.0',
    // Dev-only server: HMR client served by Vite, everything else proxied
    // to the FastAPI gateway (the single origin in production). APP_PORT
    // and NARRATIVE_API_PORT/NARRATIVE_API_URL match the gateway launcher.
    port: parseInt(process.env.APP_PORT ?? "5001", 10),
    strictPort: true,
    fs: {
      strict: true,
      deny: ["**/.*"],
    },
    proxy: (() => {
      const gateway =
        process.env.NARRATIVE_API_URL ??
        `http://localhost:${process.env.NARRATIVE_API_PORT ?? "8002"}`;
      return {
        '/api': { target: gateway, changeOrigin: true },
        '/ws': { target: gateway, ws: true, changeOrigin: true },
        // Runtime upload dirs: the gateway serves the same files Vite
        // mirrors from client/public; proxying keeps one source of truth.
        '/character_portraits': { target: gateway, changeOrigin: true },
        '/place_images': { target: gateway, changeOrigin: true },
      };
    })(),
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: path.resolve(import.meta.dirname, "client", "src", "tests", "setup.ts"),
    css: true,
  },
});
