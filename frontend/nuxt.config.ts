// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui',
    '@vite-pwa/nuxt'
  ],

  // Reine SPA: die App ist ein persoenliches Karaoke-Tool ohne SEO-Bedarf, haengt
  // an Browser-APIs (Web Audio, getUserMedia, IndexedDB) und soll offline laufen.
  // SSR wuerde hier nur Hydration-Mismatches und einen Node-Server beim Deploy
  // bringen - so reicht `nuxt generate` + statisches HTTPS-Hosting.
  ssr: false,

  devtools: {
    enabled: true
  },

  app: {
    head: {
      htmlAttrs: { lang: 'de' },
      link: [
        { rel: 'apple-touch-icon', href: '/apple-touch-icon-180x180.png' }
      ]
    }
  },

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    public: {
      // Adresse des Spring-Boot-Backends. In Produktion (Tailscale) per
      // NUXT_PUBLIC_API_BASE env var auf die Tailscale-IP/MagicDNS-Namen setzen.
      // Leer lassen ist erlaubt: dann laeuft die App rein offline mit den
      // importierten .ksong-Songs aus der Geraete-Bibliothek.
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
    manifest: {
      name: 'Karaoke App',
      short_name: 'Karaoke',
      description: 'Mitsing-App mit Note-Highway und Live-Tonhoehen-Feedback. Songs offline importieren (.ksong).',
      lang: 'de',
      theme_color: '#059669',
      background_color: '#ffffff',
      display: 'standalone',
      orientation: 'portrait',
      start_url: '/',
      scope: '/',
      icons: [
        { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
        { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        { src: '/maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
      ]
    },
    workbox: {
      // App-Shell + Assets vorab cachen, damit die App ohne Netz startet.
      // .ksong-Songdaten liegen in IndexedDB, brauchen also kein SW-Caching.
      globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
      navigateFallback: '/',
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
