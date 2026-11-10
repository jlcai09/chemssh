import type { Terminal } from '@xterm/xterm'

/**
 * The slice of xterm a history guard needs. `Terminal` satisfies it, and the
 * narrow shape keeps the guard testable without a live terminal.
 */
export interface TerminalHistoryScreen {
  readonly rows: number
  readonly buffer: {
    readonly active: {
      readonly type: 'normal' | 'alternate'
      readonly baseY: number
      getLine(y: number): { translateToString(trimRight?: boolean): string } | undefined
    }
  }
  scrollToBottom(): void
}

/**
 * `CSI 2 J` erases the display, `CSI 3 J` erases the saved scrollback.
 * `CSI J` on its own is deliberately not matched: readline emits it while a
 * line is being edited, and treating that as a screen wipe would scroll the
 * terminal on every keystroke.
 */
const ERASE_DISPLAY = /\x1b\[(?:2J|3J)/g

/**
 * `top`, `clear` and other screen-owning programs erase the display before they
 * draw. xterm honours that literally, so the rows the user was reading vanish.
 * ChemSSH keeps a long scrollback per tab, so the visible rows are moved into
 * the scrollback first and a scrollback wipe is ignored outright.
 */
export function preserveTerminalHistory(screen: TerminalHistoryScreen, data: string): string {
  if (!data.includes('\x1b[')) return data
  let out = ''
  let index = 0
  let matched = false
  for (const match of data.matchAll(ERASE_DISPLAY)) {
    matched = true
    const at = match.index ?? 0
    out += data.slice(index, at)
    index = at + match[0].length
    // No remote program may throw away this tab's scrollback.
    if (match[0].endsWith('3J')) continue
    out += scrollScreenIntoScrollback(screen)
    out += match[0]
  }
  return matched ? out + data.slice(index) : data
}

/**
 * Scrolls every visible row into the scrollback, then homes the cursor, which
 * is where a program expects to be after erasing the display. The erase the
 * caller appends afterwards therefore only clears blank rows.
 */
export function scrollScreenIntoScrollback(screen: TerminalHistoryScreen): string {
  const buffer = screen.buffer.active
  // The alternate screen has no scrollback worth saving and is restored as a
  // whole when the program exits.
  if (buffer.type !== 'normal' || screen.rows < 1) return ''
  screen.scrollToBottom()
  let usedRows = 0
  for (let row = screen.rows - 1; row >= 0; row -= 1) {
    const line = buffer.getLine(buffer.baseY + row)
    if (line && line.translateToString(true).trim() !== '') {
      usedRows = row + 1
      break
    }
  }
  if (usedRows === 0) return ''
  return `\x1b[${screen.rows};1H${'\r\n'.repeat(usedRows)}\x1b[H`
}

/** Writes terminal output after applying the history guard. */
export function writePreservingTerminalHistory(terminal: Terminal, data: string) {
  terminal.write(preserveTerminalHistory(terminal, data))
}
