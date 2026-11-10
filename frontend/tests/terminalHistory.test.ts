import assert from 'node:assert/strict'
import {
  preserveTerminalHistory,
  scrollScreenIntoScrollback,
  type TerminalHistoryScreen
} from '../src/utils/terminalHistory.ts'

// `lines` is indexed like the real buffer: 0 is the oldest scrollback row and
// `baseY` is the first row of the viewport.
function fakeScreen(options: {
  rows: number
  lines: string[]
  type?: 'normal' | 'alternate'
  baseY?: number
}): TerminalHistoryScreen {
  return {
    rows: options.rows,
    buffer: {
      active: {
        type: options.type ?? 'normal',
        baseY: options.baseY ?? 0,
        getLine: (y: number) => {
          const text = options.lines[y]
          return text === undefined ? undefined : { translateToString: () => text }
        }
      }
    },
    scrollToBottom: () => undefined
  }
}

// Plain output never changes.
assert.equal(preserveTerminalHistory(fakeScreen({ rows: 5, lines: [] }), 'hello\r\nworld'), 'hello\r\nworld')

// `CSI 2 J` keeps the visible rows: they are scrolled into the scrollback and
// the cursor is homed before the erase reaches the terminal.
const twoRows = fakeScreen({ rows: 5, lines: ['$ ls', 'a b c', '', '', ''] })
assert.equal(
  preserveTerminalHistory(twoRows, '\x1b[H\x1b[2Jdone'),
  `\x1b[H\x1b[5;1H\r\n\r\n\x1b[H\x1b[2Jdone`
)

// A blank screen has nothing to save, so the erase is passed through as is.
assert.equal(preserveTerminalHistory(fakeScreen({ rows: 4, lines: [] }), '\x1b[2J'), '\x1b[2J')

// `CSI 3 J` would erase the scrollback: it is dropped, never forwarded.
assert.equal(preserveTerminalHistory(fakeScreen({ rows: 3, lines: ['keep me'] }), 'tail\x1b[3Jmore'), 'tailmore')
assert.equal(preserveTerminalHistory(fakeScreen({ rows: 3, lines: ['keep me'] }), '\x1b[3J'), '')

// Readline's `CSI J` (erase to end of line) must not trigger a scroll.
assert.equal(preserveTerminalHistory(fakeScreen({ rows: 5, lines: ['$ ls -l'] }), '\r\x1b[J$ ls -la'), '\r\x1b[J$ ls -la')

// The alternate screen has no scrollback to protect: full-screen programs keep
// the sequences they sent.
assert.equal(preserveTerminalHistory(fakeScreen({ rows: 5, lines: ['top'], type: 'alternate' }), '\x1b[2J'), '\x1b[2J')
assert.equal(scrollScreenIntoScrollback(fakeScreen({ rows: 5, lines: ['top'], type: 'alternate' })), '')

// A private-mode erase (`CSI ? 2 J`) is not a display wipe.
assert.equal(preserveTerminalHistory(fakeScreen({ rows: 5, lines: ['x'] }), '\x1b[?2J'), '\x1b[?2J')

// Only rows that carry text are saved; the viewport is aligned to the buffer
// end first, so a scrolled-back viewport cannot park the cursor mid-history.
assert.equal(scrollScreenIntoScrollback(fakeScreen({ rows: 4, lines: ['', '', 'log', ''] })), '\x1b[4;1H\r\n\r\n\r\n\x1b[H')
assert.equal(scrollScreenIntoScrollback(fakeScreen({ rows: 4, lines: ['', '', '', ''] })), '')

// Scrollback rows outside the viewport are ignored when counting.
assert.equal(
  scrollScreenIntoScrollback(fakeScreen({ rows: 2, lines: ['older', 'older', 'visible', ''], baseY: 2 })),
  '\x1b[2;1H\r\n\x1b[H'
)
