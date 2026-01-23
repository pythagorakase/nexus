import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'icons/apple-touch-icon.png'],
      manifest: {
        name: 'NEXUS',
        short_name: 'NEXUS',
        description: 'NEXUS - Narrative exploration and analysis',
        theme_color: '#0d9488',
        background_color: '#09090b',
        display: 'standalone',
        orientation: 'any',
        icons: [
          {
            src: '/icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/icons/apple-touch-icon.png',
            sizes: '180x180',
            type: 'image/png',
            purpose: 'any'
          }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
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
    fs: {
      strict: true,
      deny: ["**/.*"],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: path.resolve(import.meta.dirname, "client", "src", "tests", "setup.ts"),
    css: true,
  },
});
