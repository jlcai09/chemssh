import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'

const require = createRequire(import.meta.url)
const ts = require('typescript')
const source = readFileSync(new URL('../src/components/FileTree.vue', import.meta.url), 'utf8')

function componentFunction(name: string) {
  const start = source.indexOf(`function ${name}(`)
  assert.notEqual(start, -1)
  const end = source.indexOf('\n}\n', start)
  return source.slice(start, end + 2)
}

function harness() {
  let activeElement: unknown = 'terminal'
  let deleteCount = 0
  let selectionUpdates = 0
  const body = {
    focus(options: { preventScroll: boolean }) {
      assert.equal(options.preventScroll, true)
      activeElement = body
    }
  }
  const props = { selectedItems: [{ path: '/workspace/a' }, { path: '/workspace/b' }] }
  const context: Record<string, any> = {
    props, bodyRef: { value: body }, Element: class {},
    isScrollbarEvent: () => false,
    window: { addEventListener() {}, removeEventListener() {} },
    dragActive: { value: false }, dragAnchor: { value: null }, dragOverIndex: { value: null },
    blankDragActive: { value: false }, blankDragPathSet: { value: new Set() },
    exportDragActive: { value: false },
    updateBlankDragSelection: () => { selectionUpdates += 1 },
    finishFileDrag() {}, resetPressState() {}, handleBlankDragMove() {},
    emit: (name: string) => { if (name === 'delete') deleteCount += 1 }
  }
  const program = ts.transpileModule([
    'let blankDragStartX, blankDragStartY, blankDragCurrentX, blankDragCurrentY;',
    componentFunction('beginBlankSelect'), componentFunction('finishSelection'), componentFunction('handleKeydown'),
    'this.beginBlankSelect = beginBlankSelect; this.finishSelection = finishSelection; this.handleKeydown = handleKeydown;'
  ].join('\n'), { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText
  runInNewContext(program, context)
  return {
    context, body, props,
    get activeElement() { return activeElement },
    get deleteCount() { return deleteCount },
    get selectionUpdates() { return selectionUpdates }
  }
}

function key(overrides = {}) {
  return { key: 'Delete', repeat: false, ctrlKey: false, metaKey: false, altKey: false,
    shiftKey: false, preventDefault() {}, ...overrides }
}

test('blank selection takes focus from terminal and first Delete handles all selected files', () => {
  const h = harness()
  assert.equal(h.activeElement, 'terminal')
  h.context.beginBlankSelect({ target: null, clientX: 10, clientY: 20, preventDefault() {} })
  assert.equal(h.activeElement, h.body)
  assert.equal(h.selectionUpdates, 1)
  h.context.finishSelection()
  h.context.handleKeydown(0, key())
  assert.equal(h.deleteCount, 1)
  assert.equal(h.props.selectedItems.length, 2)
  // Cancelling the parent's confirmation leaves selection intact; retry works.
  h.context.handleKeydown(0, key())
  assert.equal(h.deleteCount, 2)
})

test('Delete ignores repeats, modifiers and empty selection', () => {
  const h = harness()
  for (const modifier of ['repeat', 'ctrlKey', 'metaKey', 'altKey', 'shiftKey']) {
    h.context.handleKeydown(0, key({ [modifier]: true }))
  }
  h.props.selectedItems = []
  h.context.handleKeydown(0, key())
  assert.equal(h.deleteCount, 0)
})

test('body handles only its own keyboard events, leaving row handlers single-fired', () => {
  assert.match(source, /ref="bodyRef"[\s\S]*?tabindex="-1"[\s\S]*?@keydown\.self="handleKeydown\(focusedIndex \?\? 0, \$event\)"/)
  assert.match(source, /@keydown="handleKeydown\(index, \$event\)"/)
})
