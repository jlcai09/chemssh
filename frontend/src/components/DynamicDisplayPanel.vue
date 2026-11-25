<template>
  <div class="dynamic-display-panel" @pointerdown.stop @wheel.stop>
    <div class="ddp-header">
      <div class="ddp-title-group">
        <strong>{{ t('viewer.dynamicRules.title') }}</strong>
        <span class="ddp-subtitle">{{ t('viewer.dynamicRules.subtitle') }}</span>
      </div>
      <div class="ddp-header-actions">
        <el-button v-if="rules.length > 0" size="small" text type="danger" @click="clearAll">
          {{ t('viewer.dynamicRules.clearAll') }}
        </el-button>
        <button class="ddp-close" type="button" :aria-label="t('panel.close')" @click="$emit('close')">
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </div>

    <div class="ddp-presets">
      <span class="ddp-section-label">{{ t('viewer.dynamicRules.presets') }}</span>
      <div class="ddp-preset-chips">
        <button type="button" class="ddp-chip" @click="applyPreset('hide-water')">
          {{ t('viewer.dynamicRules.presetHideWater') }}
        </button>
        <button type="button" class="ddp-chip" @click="applyPreset('dim-solvent')">
          {{ t('viewer.dynamicRules.presetDimSolvent') }}
        </button>
        <button type="button" class="ddp-chip" @click="applyPreset('minority')">
          {{ t('viewer.dynamicRules.presetMinority') }}
        </button>
        <button type="button" class="ddp-chip" @click="applyPreset('dim-fixed')">
          {{ t('viewer.dynamicRules.presetDimFixed') }}
        </button>
      </div>
    </div>

    <div class="ddp-list">
      <div v-if="rules.length === 0 && !editorOpen" class="ddp-empty">
        {{ t('viewer.dynamicRules.empty') }}
      </div>

      <div
        v-for="(rule, idx) in rules"
        :key="rule.id"
        class="ddp-card"
        :class="{ 'is-disabled': !rule.enabled }"
      >
        <div class="ddp-card-top">
          <el-checkbox
            :model-value="rule.enabled"
            size="small"
            @change="(val: unknown) => toggleRule(rule.id, Boolean(val))"
          />
          <span class="ddp-card-summary" :title="ruleSummary(rule)">
            {{ idx + 1 }}. {{ ruleSummary(rule) }}
          </span>
          <span v-if="rule.enabled && matchCounts[rule.id] !== undefined" class="ddp-match-badge">
            {{ t('viewer.dynamicRules.matchedAtoms', { count: matchCounts[rule.id] }) }}
          </span>
        </div>
        <div class="ddp-card-bottom">
          <el-select
            :model-value="rule.style"
            size="small"
            class="ddp-style-select"
            :teleported="false"
            @change="(val: DynamicDisplayStyle) => updateRuleStyle(rule.id, val)"
          >
            <el-option v-for="opt in styleOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
          <div class="ddp-card-ops">
            <button type="button" class="ddp-icon-btn" :disabled="idx === 0" @click="moveRule(idx, -1)">↑</button>
            <button type="button" class="ddp-icon-btn" :disabled="idx === rules.length - 1" @click="moveRule(idx, 1)">↓</button>
            <button type="button" class="ddp-icon-btn" @click="startEdit(rule)">✎</button>
            <button type="button" class="ddp-icon-btn is-danger" @click="removeRule(rule.id)">✕</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="editorOpen" class="ddp-editor">
      <div class="ddp-field">
        <label>{{ t('viewer.dynamicRules.addRule') }}</label>
        <el-select v-model="draft.type" size="small" :teleported="false">
          <el-option value="formula" :label="t('viewer.dynamicRules.typeFormula')" />
          <el-option value="shell" :label="t('viewer.dynamicRules.typeShell')" />
          <el-option value="coordination" :label="t('viewer.dynamicRules.typeCoordination')" />
          <el-option value="slice" :label="t('viewer.dynamicRules.typeSlice')" />
          <el-option value="minority" :label="t('viewer.dynamicRules.typeMinority')" />
          <el-option value="element_fixed" :label="t('viewer.dynamicRules.typeElementFixed')" />
        </el-select>
      </div>

      <!-- 1. Formula -->
      <template v-if="draft.type === 'formula'">
        <div class="ddp-field">
          <label>{{ t('viewer.dynamicRules.formulasLabel') }}</label>
          <el-input v-model="draftFormulasText" size="small" placeholder="H2O, CH3OH" />
        </div>
        <div v-if="availableFormulas.length > 0" class="ddp-formula-hints">
          <button
            v-for="f in availableFormulas.slice(0, 8)"
            :key="f"
            type="button"
            class="ddp-mini-chip"
            @click="appendFormulaHint(f)"
          >
            {{ f }}
          </button>
        </div>
      </template>

      <!-- 2. Distance Shell -->
      <template v-else-if="draft.type === 'shell'">
        <div class="ddp-field">
          <label>{{ t('viewer.dynamicRules.anchorType') }}</label>
          <el-select v-model="draft.anchor_type" size="small" :teleported="false">
            <el-option value="elements" :label="t('viewer.dynamicRules.anchorElements')" />
            <el-option value="atoms" :label="t('viewer.dynamicRules.anchorAtoms')" />
          </el-select>
        </div>
        <div v-if="draft.anchor_type === 'elements'" class="ddp-field">
          <label>{{ t('viewer.dynamicRules.elementsLabel') }}</label>
          <el-input v-model="draftAnchorElementsText" size="small" placeholder="La, Na, Pt" />
        </div>
        <div class="ddp-row">
          <el-select v-model="draft.outside" size="small" :teleported="false" style="width: 112px">
            <el-option :value="false" :label="t('viewer.dynamicRules.inside')" />
            <el-option :value="true" :label="t('viewer.dynamicRules.outside')" />
          </el-select>
          <el-input-number v-model="draft.radius" :min="0.5" :max="50" :step="0.5" :precision="2" size="small" />
        </div>
        <el-checkbox v-model="draft.expand_fragments" size="small">
          {{ t('viewer.radiusExpandFragments') }}
        </el-checkbox>
      </template>

      <!-- 3. Coordination -->
      <template v-else-if="draft.type === 'coordination'">
        <div class="ddp-field">
          <label>{{ t('viewer.dynamicRules.elementsLabel') }}</label>
          <el-input v-model="draftElementsText" size="small" placeholder="O" />
        </div>
        <div class="ddp-row">
          <el-select v-model="draft.operator" size="small" :teleported="false" style="width: 96px">
            <el-option value="ne" label="≠" />
            <el-option value="eq" label="=" />
            <el-option value="lt" label="<" />
            <el-option value="le" label="≤" />
            <el-option value="gt" label=">" />
            <el-option value="ge" label="≥" />
          </el-select>
          <el-input-number v-model="draft.count" :min="0" :max="32" :step="1" size="small" />
        </div>
        <el-checkbox v-model="draft.expand_fragments" size="small">
          {{ t('viewer.radiusExpandFragments') }}
        </el-checkbox>
      </template>

      <!-- 4. Spatial Slice -->
      <template v-else-if="draft.type === 'slice'">
        <div class="ddp-row">
          <el-select v-model="draft.axis" size="small" :teleported="false" style="width: 72px">
            <el-option value="x" label="X" />
            <el-option value="y" label="Y" />
            <el-option value="z" label="Z" />
          </el-select>
          <el-select v-model="draft.outside" size="small" :teleported="false" style="flex: 1">
            <el-option :value="false" :label="t('viewer.dynamicRules.inside')" />
            <el-option :value="true" :label="t('viewer.dynamicRules.outside')" />
          </el-select>
        </div>
        <div class="ddp-row">
          <el-input-number
            v-model="draftSliceMin"
            :step="draft.fractional ? 0.05 : 1"
            :precision="2"
            size="small"
            :placeholder="t('viewer.dynamicRules.sliceMin')"
          />
          <span>~</span>
          <el-input-number
            v-model="draftSliceMax"
            :step="draft.fractional ? 0.05 : 1"
            :precision="2"
            size="small"
            :placeholder="t('viewer.dynamicRules.sliceMax')"
          />
        </div>
        <div class="ddp-checks">
          <el-checkbox v-model="draft.fractional" size="small" :disabled="!hasCell">
            {{ t('viewer.dynamicRules.fractional') }}
          </el-checkbox>
          <el-checkbox v-model="draft.expand_fragments" size="small">
            {{ t('viewer.radiusExpandFragments') }}
          </el-checkbox>
        </div>
      </template>

      <!-- 5. Minority / Reactive Species -->
      <template v-else-if="draft.type === 'minority'">
        <div class="ddp-field">
          <label>{{ t('viewer.dynamicRules.maxFraction') }}</label>
          <el-input-number v-model="draftMaxPercent" :min="1" :max="100" :step="1" size="small" />
        </div>
        <el-checkbox v-model="draft.invert" size="small">
          {{ t('viewer.dynamicRules.invertMajority') }}
        </el-checkbox>
      </template>

      <!-- 6. Element / Fixed -->
      <template v-else-if="draft.type === 'element_fixed'">
        <div class="ddp-field">
          <label>{{ t('viewer.dynamicRules.elementsLabel') }}</label>
          <el-input v-model="draftElementsText" size="small" placeholder="H, O" />
        </div>
        <el-checkbox v-model="draft.fixed_only" size="small">
          {{ t('viewer.dynamicRules.fixedOnly') }}
        </el-checkbox>
      </template>

      <div class="ddp-field">
        <label>{{ t('viewer.dynamicRules.targetStyle') }}</label>
        <el-select v-model="draft.style" size="small" :teleported="false">
          <el-option v-for="opt in styleOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </div>

      <div class="ddp-editor-actions">
        <el-button size="small" @click="cancelEdit">{{ t('viewer.radiusCancel') }}</el-button>
        <el-button size="small" type="primary" @click="commitDraft">{{ t('viewer.dynamicRules.apply') }}</el-button>
      </div>
    </div>

    <div v-else class="ddp-footer">
      <el-button size="small" type="primary" plain style="width: 100%" @click="startCreate">
        + {{ t('viewer.dynamicRules.addRule') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { t } from '../i18n'
import type { CoordOperator, DynamicDisplayRule, DynamicDisplayStyle, DynamicRuleType } from '../types/structure'

const props = defineProps<{
  rules: DynamicDisplayRule[]
  matchCounts: Record<string, number>
  availableFormulas: string[]
  selectedAtoms: number[]
  hasCell: boolean
}>()

const emit = defineEmits<{
  (event: 'update:rules', rules: DynamicDisplayRule[]): void
  (event: 'close'): void
}>()

const styleOptions = computed<Array<{ value: DynamicDisplayStyle; label: string }>>(() => [
  { value: 'stick', label: t('viewer.styleStick') },
  { value: 'sphere', label: t('viewer.styleSphere') },
  { value: 'line', label: t('viewer.styleLine') },
  { value: 'dim', label: t('viewer.styleDim') },
  { value: 'hidden', label: t('viewer.styleHide') }
])

const editorOpen = ref(false)
const editingRuleId = ref<string | null>(null)
const draft = reactive<{
  type: DynamicRuleType
  style: DynamicDisplayStyle
  anchor_type: 'atoms' | 'elements'
  anchor_atoms: number[]
  radius: number
  outside: boolean
  expand_fragments: boolean
  operator: CoordOperator
  count: number
  axis: 'x' | 'y' | 'z'
  fractional: boolean
  invert: boolean
  fixed_only: boolean
}>({
  type: 'formula',
  style: 'hidden',
  anchor_type: 'elements',
  anchor_atoms: [],
  radius: 3.5,
  outside: false,
  expand_fragments: true,
  operator: 'ne',
  count: 2,
  axis: 'z',
  fractional: false,
  invert: false,
  fixed_only: false
})

const draftFormulasText = ref('H2O')
const draftAnchorElementsText = ref('')
const draftElementsText = ref('')
const draftSliceMin = ref<number | undefined>(0)
const draftSliceMax = ref<number | undefined>(10)
const draftMaxPercent = ref(10)

function nextId() {
  return `rule_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`
}

function parseCsv(text: string): string[] {
  return text
    .split(/[,，\s]+/)
    .map(item => item.trim())
    .filter(Boolean)
}

function appendFormulaHint(formula: string) {
  const existing = parseCsv(draftFormulasText.value)
  if (!existing.includes(formula)) existing.push(formula)
  draftFormulasText.value = existing.join(', ')
}

function startCreate() {
  editingRuleId.value = null
  draft.type = 'formula'
  draft.style = 'hidden'
  draft.anchor_type = props.selectedAtoms.length > 0 ? 'atoms' : 'elements'
  draft.anchor_atoms = [...props.selectedAtoms]
  draft.radius = 3.5
  draft.outside = false
  draft.expand_fragments = true
  draft.operator = 'ne'
  draft.count = 2
  draft.axis = 'z'
  draft.fractional = false
  draft.invert = false
  draft.fixed_only = false
  draftFormulasText.value = props.availableFormulas[0] || 'H2O'
  draftAnchorElementsText.value = ''
  draftElementsText.value = ''
  draftSliceMin.value = 0
  draftSliceMax.value = 10
  draftMaxPercent.value = 10
  editorOpen.value = true
}

function startEdit(rule: DynamicDisplayRule) {
  editingRuleId.value = rule.id
  draft.type = rule.type
  draft.style = rule.style
  draft.anchor_type = rule.anchor_type ?? 'elements'
  draft.anchor_atoms = [...(rule.anchor_atoms ?? [])]
  draft.radius = rule.radius ?? 3.5
  draft.outside = Boolean(rule.outside)
  draft.expand_fragments = rule.expand_fragments ?? true
  draft.operator = rule.operator ?? 'ne'
  draft.count = rule.count ?? 2
  draft.axis = rule.axis ?? 'z'
  draft.fractional = Boolean(rule.fractional)
  draft.invert = Boolean(rule.invert)
  draft.fixed_only = Boolean(rule.fixed_only)
  draftFormulasText.value = (rule.formulas ?? []).join(', ')
  draftAnchorElementsText.value = (rule.anchor_elements ?? []).join(', ')
  draftElementsText.value = (rule.elements ?? []).join(', ')
  draftSliceMin.value = rule.min_val ?? undefined
  draftSliceMax.value = rule.max_val ?? undefined
  draftMaxPercent.value = Math.round((rule.max_fraction ?? 0.05) * 100)
  editorOpen.value = true
}

function cancelEdit() {
  editorOpen.value = false
  editingRuleId.value = null
}

function commitDraft() {
  const newRule: DynamicDisplayRule = {
    id: editingRuleId.value ?? nextId(),
    enabled: true,
    type: draft.type,
    style: draft.style
  }
  if (draft.type === 'formula') {
    newRule.formulas = parseCsv(draftFormulasText.value)
  } else if (draft.type === 'shell') {
    newRule.anchor_type = draft.anchor_type
    newRule.anchor_atoms = draft.anchor_type === 'atoms'
      ? (draft.anchor_atoms.length ? draft.anchor_atoms : [...props.selectedAtoms])
      : []
    newRule.anchor_elements = draft.anchor_type === 'elements' ? parseCsv(draftAnchorElementsText.value) : []
    newRule.radius = draft.radius
    newRule.outside = draft.outside
    newRule.expand_fragments = draft.expand_fragments
  } else if (draft.type === 'coordination') {
    newRule.elements = parseCsv(draftElementsText.value)
    newRule.operator = draft.operator
    newRule.count = draft.count
    newRule.expand_fragments = draft.expand_fragments
  } else if (draft.type === 'slice') {
    newRule.axis = draft.axis
    newRule.min_val = draftSliceMin.value ?? null
    newRule.max_val = draftSliceMax.value ?? null
    newRule.fractional = draft.fractional
    newRule.outside = draft.outside
    newRule.expand_fragments = draft.expand_fragments
  } else if (draft.type === 'minority') {
    newRule.max_fraction = Math.min(1, Math.max(0.01, draftMaxPercent.value / 100))
    newRule.invert = draft.invert
  } else if (draft.type === 'element_fixed') {
    newRule.elements = parseCsv(draftElementsText.value)
    newRule.fixed_only = draft.fixed_only
  }

  const next = [...props.rules]
  if (editingRuleId.value) {
    const idx = next.findIndex(r => r.id === editingRuleId.value)
    if (idx >= 0) next[idx] = { ...newRule, enabled: next[idx].enabled }
    else next.push(newRule)
  } else {
    next.push(newRule)
  }
  emit('update:rules', next)
  editorOpen.value = false
  editingRuleId.value = null
}

function toggleRule(id: string, enabled: boolean) {
  emit('update:rules', props.rules.map(r => (r.id === id ? { ...r, enabled } : r)))
}

function updateRuleStyle(id: string, style: DynamicDisplayStyle) {
  emit('update:rules', props.rules.map(r => (r.id === id ? { ...r, style } : r)))
}

function moveRule(index: number, delta: -1 | 1) {
  const target = index + delta
  if (target < 0 || target >= props.rules.length) return
  const next = [...props.rules]
  const [item] = next.splice(index, 1)
  next.splice(target, 0, item)
  emit('update:rules', next)
}

function removeRule(id: string) {
  emit('update:rules', props.rules.filter(r => r.id !== id))
}

function clearAll() {
  emit('update:rules', [])
}

function applyPreset(preset: 'hide-water' | 'dim-solvent' | 'minority' | 'dim-fixed') {
  const next = [...props.rules]
  if (preset === 'hide-water') {
    next.push({ id: nextId(), enabled: true, type: 'formula', style: 'hidden', formulas: ['H2O'] })
  } else if (preset === 'dim-solvent') {
    next.push({ id: nextId(), enabled: true, type: 'minority', style: 'dim', max_fraction: 0.15, invert: true })
  } else if (preset === 'minority') {
    next.push({ id: nextId(), enabled: true, type: 'minority', style: 'dim', max_fraction: 0.1, invert: true })
    next.push({ id: nextId(), enabled: true, type: 'minority', style: 'stick', max_fraction: 0.1, invert: false })
  } else if (preset === 'dim-fixed') {
    next.push({ id: nextId(), enabled: true, type: 'element_fixed', style: 'dim', elements: [], fixed_only: true })
  }
  emit('update:rules', next)
}

const OP_SYMBOLS: Record<CoordOperator, string> = {
  eq: '=',
  ne: '≠',
  lt: '<',
  le: '≤',
  gt: '>',
  ge: '≥'
}

function ruleSummary(rule: DynamicDisplayRule): string {
  switch (rule.type) {
    case 'formula':
      return `${t('viewer.dynamicRules.typeFormula')}: ${(rule.formulas ?? []).join(', ') || '-'}`
    case 'shell': {
      const anchor = rule.anchor_type === 'atoms'
        ? `#${(rule.anchor_atoms ?? []).slice(0, 3).join(',')}`
        : (rule.anchor_elements ?? []).join(',') || '-'
      const dir = rule.outside ? '>' : '≤'
      return `${anchor} ${dir} ${rule.radius ?? 3.5} Å`
    }
    case 'coordination': {
      const els = (rule.elements ?? []).join(',') || '*'
      return `CN(${els}) ${OP_SYMBOLS[rule.operator ?? 'ne']} ${rule.count ?? 2}`
    }
    case 'slice': {
      const axis = (rule.axis ?? 'z').toUpperCase()
      const minStr = rule.min_val ?? '-∞'
      const maxStr = rule.max_val ?? '+∞'
      return `${axis}${rule.outside ? ' ∉ ' : ' ∈ '}[${minStr}, ${maxStr}]`
    }
    case 'minority': {
      const pct = Math.round((rule.max_fraction ?? 0.05) * 100)
      return rule.invert
        ? `${t('viewer.dynamicRules.presetDimSolvent')} (>${pct}%)`
        : `${t('viewer.dynamicRules.typeMinority')} (≤${pct}%)`
    }
    case 'element_fixed': {
      const els = (rule.elements ?? []).join(',')
      if (rule.fixed_only && els) return `Fixed & ${els}`
      if (rule.fixed_only) return t('viewer.dynamicRules.fixedOnly')
      return els || '-'
    }
  }
}
</script>

<style scoped>
.dynamic-display-panel {
  position: absolute;
  top: 12px;
  left: 52px;
  z-index: 30;
  width: 306px;
  max-height: calc(100% - 24px);
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--el-bg-color-overlay, rgba(255, 255, 255, 0.96));
  border: 1px solid var(--el-border-color-light, rgba(148, 163, 184, 0.35));
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(12px);
  font-size: 12px;
  color: var(--el-text-color-primary, #1f2937);
}

.ddp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ddp-title-group {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.ddp-subtitle {
  font-size: 11px;
  color: var(--el-text-color-secondary, #6b7280);
}

.ddp-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ddp-close {
  border: none;
  background: transparent;
  color: var(--el-text-color-secondary, #6b7280);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
}

.ddp-close:hover {
  background: var(--el-fill-color-light, rgba(148, 163, 184, 0.16));
  color: var(--el-text-color-primary, #1f2937);
}

.ddp-presets {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ddp-section-label {
  font-size: 11px;
  color: var(--el-text-color-secondary, #6b7280);
}

.ddp-preset-chips,
.ddp-formula-hints {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.ddp-chip,
.ddp-mini-chip {
  border: 1px solid var(--el-border-color, rgba(148, 163, 184, 0.4));
  background: var(--el-fill-color-blank, #ffffff);
  color: var(--el-text-color-regular, #374151);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 11px;
  cursor: pointer;
  transition: background-color 0.12s ease, border-color 0.12s ease, color 0.12s ease;
}

.ddp-chip:hover,
.ddp-mini-chip:hover {
  border-color: var(--el-color-primary, #2563eb);
  color: var(--el-color-primary, #2563eb);
  background: var(--el-color-primary-light-9, rgba(37, 99, 235, 0.08));
}

.ddp-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  max-height: 240px;
}

.ddp-empty {
  padding: 10px 8px;
  text-align: center;
  color: var(--el-text-color-secondary, #6b7280);
  font-size: 11.5px;
  border: 1px dashed var(--el-border-color, rgba(148, 163, 184, 0.4));
  border-radius: 8px;
}

.ddp-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 7px 8px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter, rgba(148, 163, 184, 0.3));
  background: var(--el-fill-color-lighter, rgba(248, 250, 252, 0.85));
}

.ddp-card.is-disabled {
  opacity: 0.58;
}

.ddp-card-top {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ddp-card-summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.ddp-match-badge {
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--el-color-primary-light-9, rgba(37, 99, 235, 0.1));
  color: var(--el-color-primary, #2563eb);
  flex-shrink: 0;
}

.ddp-card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.ddp-style-select {
  width: 112px;
}

.ddp-card-ops {
  display: flex;
  align-items: center;
  gap: 2px;
}

.ddp-icon-btn {
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--el-text-color-regular, #4b5563);
  cursor: pointer;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ddp-icon-btn:hover:not(:disabled) {
  background: var(--el-fill-color, rgba(148, 163, 184, 0.2));
}

.ddp-icon-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.ddp-icon-btn.is-danger:hover {
  color: var(--el-color-danger, #dc2626);
}

.ddp-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--el-border-color-lighter, rgba(148, 163, 184, 0.28));
}

.ddp-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ddp-field label {
  font-size: 11px;
  color: var(--el-text-color-secondary, #6b7280);
}

.ddp-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ddp-checks {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ddp-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}
</style>
