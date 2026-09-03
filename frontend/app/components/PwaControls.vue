<script setup lang="ts">
// Kleine PWA-Leiste: "App installieren" (wenn der Browser einen Install-Prompt
// anbietet) und "Update verfuegbar" (wenn der Service Worker eine neue Version
// vorhaelt). $pwa kommt von @vite-pwa/nuxt und ist erst clientseitig da.
const { $pwa } = useNuxtApp()
</script>

<template>
  <div
    v-if="$pwa && ($pwa.needRefresh || ($pwa.showInstallPrompt && !$pwa.isPWAInstalled))"
    class="border-b border-default bg-elevated"
  >
    <div class="max-w-3xl mx-auto w-full px-4 py-2 flex items-center gap-3 text-sm">
      <template v-if="$pwa.needRefresh">
        <span class="text-muted">Neue Version verfügbar.</span>
        <UButton
          size="xs"
          @click="$pwa.updateServiceWorker(true)"
        >
          Aktualisieren
        </UButton>
      </template>
      <template v-else>
        <span class="text-muted">Als App installieren – läuft dann auch offline.</span>
        <UButton
          size="xs"
          icon="i-lucide-download"
          @click="$pwa!.install()"
        >
          Installieren
        </UButton>
        <UButton
          size="xs"
          variant="ghost"
          color="neutral"
          @click="$pwa!.cancelInstall()"
        >
          Später
        </UButton>
      </template>
    </div>
  </div>
</template>
