// https://nuxt.com/docs/api/configuration/nuxt-config

// Basis-Pfad: lokal "/", auf GitHub Pages "/karaoke-app/" (per NUXT_APP_BASE_URL
// im Deploy-Workflow gesetzt). Wird fuer app.baseURL, die PWA-Icons und den
// Service-Worker-Fallback gebraucht.
const baseURL = process.env.NUXT_APP_BASE_URL || '/'

export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@vite-pwa/nuxt'
  ],

  // Reine SPA: die App ist ein persoenliches Karaoke-Tool ohne SEO-Bedarf, haengt
  // an Browser-APIs (Web Audio, getUserMedia, IndexedDB) und soll offline laufen.
  // SSR wuerde hier nur Hydration-Mismatches und einen Node-Server beim Deploy
  // bringen - so reicht `nuxt generate` + statisches HTTPS-Hosting (GitHub Pages).
  ssr: false,

  devtools: {
    enabled: true
  },

  app: {
    baseURL,
    head: {
      htmlAttrs: { lang: 'de' },
      link: [
        { rel: 'apple-touch-icon', href: `${baseURL}apple-touch-icon-180x180.png` }
      ]
    }
  },

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    public: {
      // Adresse des Spring-Boot-Backends. Per NUXT_PUBLIC_API_BASE ueberschreibbar
      // (Tailscale-IP/MagicDNS in Produktion; leer im GitHub-Pages-Build - dort
      // laeuft die App rein offline mit den importierten .ksong-Songs).
      apiBase: 'http://localhost:8080'
    }
  },

  compatibilityDate: '2026-06-30',

  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  },

  pwa: {
    registerType: 'autoUpdate',
    // start_url / scope / id leitet das Modul aus app.baseURL ab - hier bewusst
    // nicht hart auf "/" setzen, sonst bricht die installierte PWA unter /karaoke-app/.
    manifest: {
      name: 'Karaoke App',
      short_name: 'Karaoke',
      description: 'Mitsing-App mit Note-Highway und Live-Tonhoehen-Feedback. Songs offline importieren (.ksong).',
      lang: 'de',
      theme_color: '#059669',
      background_color: '#ffffff',
      display: 'standalone',
      orientation: 'portrait',
      icons: [
        { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
        { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        { src: 'maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
      ]
    },
    workbox: {
      // App-Shell + Assets vorab cachen, damit die App ohne Netz startet.
      // .ksong-Songdaten liegen sonst in IndexedDB und brauchen kein SW-Caching -
      // Ausnahme sind die Demo-Songs unter public/seed-songs/, die das
      // seed-demo-songs-Plugin auch beim allerersten Offline-Start importieren
      // koennen soll.
      globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2,ksong}'],
      // Default-Limit ist 2 MiB - amazing-grace.ksong (~2,74 MB) faellt sonst
      // stillschweigend aus dem Precache-Manifest (nur eine Warnung lokal,
      // im CI-Build aber ein harter Fehler). Grosszuegig auf 5 MB gesetzt,
      // damit auch etwas groessere zukuenftige Demo-Songs noch reinpassen.
      maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
      navigateFallback: baseURL,
      cleanupOutdatedCaches: true
    },
    client: {
      installPrompt: true
    },
    devOptions: {
      // Service Worker auch im `npm run dev` aktiv, damit man ihn testen kann
      enabled: true,
      type: 'module'
    }
  }
})
