<script setup>
useHead({
  meta: [
    { name: 'viewport', content: 'width=device-width, initial-scale=1' }
  ],
  htmlAttrs: {
    lang: 'de'
  }
})

useSeoMeta({
  title: 'Karaoke App',
  description: 'Karaoke fürs Chorüben - Songs registrieren, abspielen, Töne treffen.'
})
</script>

<template>
  <UApp>
    <UHeader>
      <template #left>
        <NuxtLink
          to="/"
          class="font-semibold text-lg"
        >
          🎤 Karaoke App
        </NuxtLink>
      </template>

      <template #right>
        <UColorModeButton />
      </template>
    </UHeader>

    <PwaControls />

    <UMain class="max-w-3xl mx-auto w-full p-4">
      <NuxtPage />
    </UMain>
  </UApp>
</template>
