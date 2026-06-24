import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getClientPreferences,
  normalizeThemePreferences,
  saveClientPreferencesPatch,
  DEFAULT_THEME_PREFERENCES
} from '../api/clientPreferences'
import type { ThemePreferences } from '../types/canvasBoard'

export const usePreferencesStore = defineStore('chemssh-preferences', () => {
  const themePreferences = ref<ThemePreferences>(normalizeThemePreferences())

  function setThemePreferences(next: ThemePreferences) {
    themePreferences.value = normalizeThemePreferences(next)
    void saveClientPreferencesPatch({ version: 1, theme: themePreferences.value }).catch(() => undefined)
  }

  function setThemePreference(key: keyof ThemePreferences, value: boolean) {
    setThemePreferences({ ...themePreferences.value, [key]: value })
  }

  function syncFromClientPreferences() {
    themePreferences.value = normalizeThemePreferences(getClientPreferences().theme)
  }

  function resetThemePreferences() {
    themePreferences.value = normalizeThemePreferences(DEFAULT_THEME_PREFERENCES)
  }

  return {
    themePreferences,
    setThemePreferences,
    setThemePreference,
    syncFromClientPreferences,
    resetThemePreferences
  }
})
