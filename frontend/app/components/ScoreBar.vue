<script setup lang="ts">
const props = defineProps<{
  isMicActive: boolean
  micError: string
  percentage: number
  combo: number
  bestCombo: number
  feedback: 'perfect' | 'good' | 'off' | null
}>()

defineEmits<{ toggleMic: [] }>()

const feedbackLabels: Record<string, string> = {
  perfect: 'Genau richtig!',
  good: 'Nah dran',
  off: 'Daneben'
}

const feedbackLabel = computed(() => props.feedback ? feedbackLabels[props.feedback] : 'Bereit')
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-default bg-elevated px-4 py-3">
      <div class="flex items-center gap-3">
        <UButton
          :icon="isMicActive ? 'i-lucide-mic' : 'i-lucide-mic-off'"
          :color="isMicActive ? 'primary' : 'neutral'"
          :variant="isMicActive ? 'solid' : 'subtle'"
          size="sm"
          @click="$emit('toggleMic')"
        >
          {{ isMicActive ? 'Mikrofon an' : 'Mikrofon aktivieren' }}
        </UButton>

        <span
          v-if="isMicActive"
          class="text-xs font-medium transition-colors"
          :class="{
            'text-success': feedback === 'perfect',
            'text-warning': feedback === 'good',
            'text-error': feedback === 'off',
            'text-muted': feedback === null
          }"
        >
          {{ feedbackLabel }}
        </span>
      </div>

      <div v-if="isMicActive" class="flex items-center gap-5 text-sm">
        <div class="text-right">
          <div class="font-bold">
            {{ percentage }}%
          </div>
          <div class="text-xs text-muted">
            Trefferquote
          </div>
        </div>
        <div class="text-right">
          <div class="font-bold">
            {{ combo }}
          </div>
          <div class="text-xs text-muted">
            Streak{{ bestCombo > combo ? ` (beste ${bestCombo})` : '' }}
          </div>
        </div>
      </div>
    </div>

    <UAlert v-if="micError" color="error" variant="subtle" :title="micError" />
  </div>
</template>
