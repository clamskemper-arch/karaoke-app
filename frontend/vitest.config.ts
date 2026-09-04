import { defineConfig } from 'vitest/config'

// Nur die reinen Funktionen (Pitch-Mathe) werden unit-getestet - kein Nuxt-
// Runtime, kein DOM noetig. Vue-Komponenten / composables mit Auto-Imports
// sind hier bewusst nicht abgedeckt.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['test/**/*.test.ts']
  }
})
