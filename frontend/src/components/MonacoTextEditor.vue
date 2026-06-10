<template>
  <div ref="containerRef" class="monaco-text-editor" />
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api.js'
import 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/shell/shell.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/xml/xml.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution.js'
import 'monaco-editor/esm/vs/language/css/monaco.contribution.js'
import 'monaco-editor/esm/vs/language/html/monaco.contribution.js'
import 'monaco-editor/esm/vs/language/json/monaco.contribution.js'
import 'monaco-editor/esm/vs/language/typescript/monaco.contribution.js'
import 'monaco-editor/min/vs/editor/editor.main.css'

// Worker cache for lazy loading
const workerCache = new Map<string, Worker>()

const monacoEnvironment = self as typeof self & {
  MonacoEnvironment?: {
    getWorker: (_moduleId: string, label: string) => Promise<Worker> | Worker
  }
}

// Lazy load workers on demand for better performance
monacoEnvironment.MonacoEnvironment = {
  getWorker: async (_moduleId: string, label: string) => {
    const cacheKey = `${_moduleId}:${label}`

    // Return cached worker if available
    if (workerCache.has(cacheKey)) {
      return workerCache.get(cacheKey)!
    }

    let WorkerModule

    // Dynamically import workers based on language
    if (label === 'json') {
      WorkerModule = await import('monaco-editor/esm/vs/language/json/json.worker?worker')
    } else if (label === 'css' || label === 'scss' || label === 'less') {
      WorkerModule = await import('monaco-editor/esm/vs/language/css/css.worker?worker')
    } else if (label === 'html' || label === 'handlebars' || label === 'razor') {
      WorkerModule = await import('monaco-editor/esm/vs/language/html/html.worker?worker')
    } else if (label === 'typescript' || label === 'javascript') {
      WorkerModule = await import('monaco-editor/esm/vs/language/typescript/ts.worker?worker')
    } else {
      WorkerModule = await import('monaco-editor/esm/vs/editor/editor.worker?worker')
    }

    const worker = new WorkerModule.default()
    workerCache.set(cacheKey, worker)
    return worker
  }
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    path?: string | null
    readonly?: boolean
  }>(),
  {
    path: null,
    readonly: false
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const containerRef = ref<HTMLElement | null>(null)
let editor: monaco.editor.IStandaloneCodeEditor | null = null
let syncing = false

function languageForPath(path?: string | null) {
  const name = (path ?? '').split(/[\\/]/).pop()?.toLowerCase() ?? ''
  const extension = name.includes('.') ? name.split('.').pop() : ''

  if (extension === 'py') return 'python'
  if (['sh', 'bash', 'zsh', 'csh', 'ksh', 'script'].includes(extension ?? '')) return 'shell'
  if (['js', 'mjs', 'cjs'].includes(extension ?? '')) return 'javascript'
  if (['ts', 'mts', 'cts'].includes(extension ?? '')) return 'typescript'
  if (extension === 'json') return 'json'
  if (['yaml', 'yml'].includes(extension ?? '')) return 'yaml'
  if (['html', 'htm'].includes(extension ?? '')) return 'html'
  if (extension === 'css') return 'css'
  if (['md', 'markdown'].includes(extension ?? '')) return 'markdown'
  if (['xml', 'xsd'].includes(extension ?? '')) return 'xml'
  if (['log', 'out', 'err', 'txt', 'dat', 'inp', 'in'].includes(extension ?? '')) return 'plaintext'
  if (['incar', 'poscar', 'potcar', 'kpoints', 'outcar', 'oszicar'].includes(name)) return 'plaintext'
  return 'plaintext'
}

function setEditorValue(value: string) {
  if (!editor || editor.getValue() === value) return
  syncing = true
  const model = editor.getModel()
  const position = editor.getPosition()
  const selections = editor.getSelections()
  editor.setValue(value)
  model?.setEOL(monaco.editor.EndOfLineSequence.LF)
  if (model && position) {
    editor.setPosition(position)
    editor.revealPositionInCenterIfOutsideViewport(position)
  }
  if (selections) editor.setSelections(selections)
  syncing = false
}

onMounted(async () => {
  await nextTick()
  if (!containerRef.value) return

  editor = monaco.editor.create(containerRef.value, {
    value: props.modelValue,
    language: languageForPath(props.path),
    theme: 'vs',
    readOnly: props.readonly,
    automaticLayout: false, // Disable automatic layout for better performance
    minimap: { enabled: false },
    fontFamily: '"JetBrains Mono", Consolas, "Liberation Mono", monospace',
    fontSize: 13,
    lineHeight: 21,
    mouseWheelZoom: true,
    scrollBeyondLastLine: false,
    wordWrap: 'on',
    tabSize: 2,
    renderWhitespace: 'selection'
  })
  editor.getModel()?.setEOL(monaco.editor.EndOfLineSequence.LF)

  // Manual layout control with ResizeObserver
  const resizeObserver = new ResizeObserver(() => {
    editor?.layout()
  })
  resizeObserver.observe(containerRef.value)

  // Store resizeObserver for cleanup
  ;(editor as any)._resizeObserver = resizeObserver

  editor.onDidChangeModelContent(() => {
    if (!editor || syncing) return
    emit('update:modelValue', editor.getValue())
  })
})

watch(
  () => props.modelValue,
  value => setEditorValue(value)
)

watch(
  () => props.path,
  path => {
    const model = editor?.getModel()
    if (model) monaco.editor.setModelLanguage(model, languageForPath(path))
  }
)

watch(
  () => props.readonly,
  readonly => {
    editor?.updateOptions({ readOnly: readonly })
  }
)

onBeforeUnmount(() => {
  // Clean up ResizeObserver
  const resizeObserver = (editor as any)?._resizeObserver
  if (resizeObserver) {
    resizeObserver.disconnect()
  }

  editor?.dispose()
  editor = null
})
</script>
