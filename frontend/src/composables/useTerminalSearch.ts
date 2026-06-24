import { ref, watch, type Ref } from 'vue'
import type { Terminal } from '@xterm/xterm'

interface SearchMatch {
  row: number
  col: number
  length: number
}

export interface SearchableTab {
  localId: string
  terminal: Terminal | null
  searchMatches: SearchMatch[]
  searchCurrentIndex: number
  searchHighlightFrame: number
  searchHighlightTimer: number
}

export function useTerminalSearch(activeTab: Ref<SearchableTab | null>, tabs: Ref<SearchableTab[]>) {
  const searchOpen = ref(false)
  const searchTerm = ref('')
  const searchCaseSensitive = ref(false)
  const searchRegex = ref(false)
  const searchResultIndex = ref(-1)
  const searchResultCount = ref(0)
  const searchResultIndexInput = ref(1)

  function performSearch() {
    const tab = activeTab.value
    const term = searchTerm.value

    if (!tab?.terminal || !term) {
      clearAllSearchHighlights()
      searchResultIndex.value = -1
      searchResultCount.value = 0
      return
    }

    clearSearchHighlights(tab)
    tab.searchMatches = []
    tab.searchCurrentIndex = -1

    const buffer = tab.terminal.buffer.active

    if (searchRegex.value) {
      try {
        const pattern = new RegExp(term, searchCaseSensitive.value ? 'g' : 'gi')

        for (let row = 0; row < buffer.length; row++) {
          const line = buffer.getLine(row)
          if (!line) continue

          const lineText = line.translateToString(true)
          let match: RegExpExecArray | null
          let maxIterations = 10000 // 防止极度病态正则导致的死循环

          pattern.lastIndex = 0

          while ((match = pattern.exec(lineText)) !== null) {
            if (--maxIterations <= 0) break

            if (match[0].length > 0) {
              tab.searchMatches.push({
                row,
                col: match.index,
                length: match[0].length
              })
            }

            if (match[0].length === 0) {
              pattern.lastIndex++
            }

            if (tab.searchMatches.filter(m => m.row === row).length > 1000) {
              break
            }
          }
        }
      } catch {
        clearAllSearchHighlights()
        updateSearchStatus()
        return
      }
    } else {
      for (let row = 0; row < buffer.length; row++) {
        const line = buffer.getLine(row)
        if (!line) continue

        const lineText = line.translateToString(true)
        const searchText = searchCaseSensitive.value ? lineText : lineText.toLowerCase()
        const searchFor = searchCaseSensitive.value ? term : term.toLowerCase()
        let col = searchText.indexOf(searchFor)

        while (col !== -1) {
          tab.searchMatches.push({ row, col, length: term.length })
          col = searchText.indexOf(searchFor, col + 1)
        }
      }
    }

    if (tab.searchMatches.length > 0) {
      tab.searchCurrentIndex = 0
      highlightAllMatchesInitial(tab, false)
    }

    updateSearchStatus()
  }

  function highlightAllMatchesInitial(tab: SearchableTab, shouldScroll = false) {
    if (!tab.terminal) return

    const buffer = tab.terminal.buffer.active
    const viewportY = buffer.viewportY
    const rows = tab.terminal.rows

    const rowsContainer = tab.terminal.element?.querySelector('.xterm-rows')
    if (!rowsContainer) return

    const rowElements = rowsContainer.children

    tab.searchMatches.forEach((match, index) => {
      if (match.row < viewportY || match.row >= viewportY + rows) return

      const relativeRow = match.row - viewportY
      if (relativeRow >= rowElements.length) return

      const rowElement = rowElements[relativeRow] as HTMLElement
      const isCurrent = index === tab.searchCurrentIndex

      const highlight = document.createElement('span')
      highlight.className = isCurrent ? 'chemssh-search-current' : 'chemssh-search-highlight'
      highlight.setAttribute('data-match-index', String(index))
      highlight.style.position = 'absolute'
      highlight.style.left = `${match.col}ch`
      highlight.style.width = `${match.length}ch`
      highlight.style.height = '100%'
      highlight.style.top = '0'
      highlight.style.borderRadius = '2px'
      highlight.style.pointerEvents = 'none'
      highlight.style.zIndex = isCurrent ? '1' : '0'

      if (isCurrent) {
        highlight.style.backgroundColor = 'rgba(255, 140, 0, 0.6)'
        highlight.style.border = '1px solid rgba(255, 140, 0, 0.9)'
      } else {
        highlight.style.backgroundColor = 'rgba(245, 230, 107, 0.35)'
      }

      if (rowElement.style.position !== 'relative' && rowElement.style.position !== 'absolute') {
        rowElement.style.position = 'relative'
      }

      rowElement.appendChild(highlight)
    })

    if (shouldScroll && tab.searchCurrentIndex >= 0 && tab.searchCurrentIndex < tab.searchMatches.length) {
      const match = tab.searchMatches[tab.searchCurrentIndex]
      if (
        match.row < tab.terminal.buffer.active.viewportY ||
        match.row >= tab.terminal.buffer.active.viewportY + tab.terminal.rows
      ) {
        tab.terminal.scrollToLine(match.row)
      }
    }
  }

  function highlightAllMatches(tab: SearchableTab, shouldScroll = false) {
    clearSearchHighlights(tab)
    highlightAllMatchesInitial(tab, shouldScroll)
  }

  function updateCurrentMatchHighlight(tab: SearchableTab, oldIndex: number, shouldScroll = true) {
    if (!tab.terminal) return

    const buffer = tab.terminal.buffer.active
    const viewportY = buffer.viewportY
    const rows = tab.terminal.rows

    const rowsContainer = tab.terminal.element?.querySelector('.xterm-rows')
    if (!rowsContainer) return

    if (oldIndex >= 0 && oldIndex < tab.searchMatches.length) {
      const oldMatch = tab.searchMatches[oldIndex]
      if (oldMatch.row >= viewportY && oldMatch.row < viewportY + rows) {
        const oldHighlight = rowsContainer.querySelector(`[data-match-index="${oldIndex}"]`) as HTMLElement
        if (oldHighlight) {
          oldHighlight.className = 'chemssh-search-highlight'
          oldHighlight.style.backgroundColor = 'rgba(245, 230, 107, 0.35)'
          oldHighlight.style.border = 'none'
          oldHighlight.style.zIndex = '0'
        }
      }
    }

    const newIndex = tab.searchCurrentIndex
    if (newIndex >= 0 && newIndex < tab.searchMatches.length) {
      const newMatch = tab.searchMatches[newIndex]

      if (shouldScroll && (newMatch.row < viewportY || newMatch.row >= viewportY + rows)) {
        tab.terminal.scrollToLine(newMatch.row)
        window.setTimeout(() => {
          clearSearchHighlights(tab)
          highlightAllMatchesInitial(tab, false)
        }, 10)
        return
      }

      const newHighlight = rowsContainer.querySelector(`[data-match-index="${newIndex}"]`) as HTMLElement
      if (newHighlight) {
        newHighlight.className = 'chemssh-search-current'
        newHighlight.style.backgroundColor = 'rgba(255, 140, 0, 0.6)'
        newHighlight.style.border = '1px solid rgba(255, 140, 0, 0.9)'
        newHighlight.style.zIndex = '1'
      }
    }
  }

  function clearSearchHighlights(tab: SearchableTab) {
    const decorations = tab.terminal?.element?.querySelectorAll(
      '.chemssh-search-highlight, .chemssh-search-current'
    )
    decorations?.forEach(el => el.remove())
  }

  function clearAllSearchHighlights() {
    for (const tab of tabs.value) {
      clearSearchHighlights(tab)
      if (tab.searchHighlightFrame) window.cancelAnimationFrame(tab.searchHighlightFrame)
      if (tab.searchHighlightTimer) window.clearTimeout(tab.searchHighlightTimer)
      tab.searchMatches = []
      tab.searchCurrentIndex = -1
      tab.searchHighlightFrame = 0
      tab.searchHighlightTimer = 0
    }
    searchResultIndex.value = -1
    searchResultCount.value = 0
  }

  function updateSearchStatus() {
    const tab = activeTab.value
    if (!tab) {
      searchResultIndex.value = -1
      searchResultCount.value = 0
      searchResultIndexInput.value = 1
      return
    }

    searchResultCount.value = tab.searchMatches.length
    searchResultIndex.value = tab.searchCurrentIndex
    searchResultIndexInput.value = tab.searchCurrentIndex >= 0 ? tab.searchCurrentIndex + 1 : 1
  }

  function findNextInTerminal() {
    const tab = activeTab.value
    if (!tab || tab.searchMatches.length === 0) return

    const oldIndex = tab.searchCurrentIndex
    tab.searchCurrentIndex = (tab.searchCurrentIndex + 1) % tab.searchMatches.length
    updateCurrentMatchHighlight(tab, oldIndex)
    updateSearchStatus()
  }

  function findPreviousInTerminal() {
    const tab = activeTab.value
    if (!tab || tab.searchMatches.length === 0) return

    const oldIndex = tab.searchCurrentIndex
    tab.searchCurrentIndex =
      tab.searchCurrentIndex <= 0 ? tab.searchMatches.length - 1 : tab.searchCurrentIndex - 1
    updateCurrentMatchHighlight(tab, oldIndex)
    updateSearchStatus()
  }

  function handleSearchIndexChange(value: number | undefined) {
    if (typeof value !== 'number') return
    const tab = activeTab.value
    if (!tab || tab.searchMatches.length === 0) return

    const newIndex = Math.max(0, Math.min(tab.searchMatches.length - 1, value - 1))
    const oldIndex = tab.searchCurrentIndex
    tab.searchCurrentIndex = newIndex
    updateCurrentMatchHighlight(tab, oldIndex)
    updateSearchStatus()
  }

  function scheduleSearchHighlightRefresh(tab: SearchableTab, delay = 0) {
    if (!searchOpen.value || !searchTerm.value || tab.searchMatches.length === 0) return
    if (delay > 0) {
      if (tab.searchHighlightTimer) window.clearTimeout(tab.searchHighlightTimer)
      tab.searchHighlightTimer = window.setTimeout(() => {
        tab.searchHighlightTimer = 0
        scheduleSearchHighlightRefresh(tab)
      }, delay)
      return
    }
    if (tab.searchHighlightFrame) return
    tab.searchHighlightFrame = window.requestAnimationFrame(() => {
      tab.searchHighlightFrame = 0
      if (!searchOpen.value || !searchTerm.value || !tab.terminal || tab.searchMatches.length === 0) return
      highlightAllMatches(tab, false)
    })
  }

  function scheduleSearchHighlightRefreshAfterInteraction(tab: SearchableTab) {
    scheduleSearchHighlightRefresh(tab)
    scheduleSearchHighlightRefresh(tab, 40)
  }

  function syncSearchWithActiveTab() {
    if (!searchOpen.value || !searchTerm.value) {
      searchResultIndex.value = -1
      searchResultCount.value = 0
      return
    }
    performSearch()
  }

  function closeSearchPanel() {
    searchOpen.value = false
    clearAllSearchHighlights()
  }

  watch([searchTerm, searchCaseSensitive, searchRegex], () => {
    if (!searchOpen.value) return
    performSearch()
  })

  return {
    searchOpen,
    searchTerm,
    searchCaseSensitive,
    searchRegex,
    searchResultIndex,
    searchResultCount,
    searchResultIndexInput,
    performSearch,
    findNextInTerminal,
    findPreviousInTerminal,
    handleSearchIndexChange,
    scheduleSearchHighlightRefresh,
    scheduleSearchHighlightRefreshAfterInteraction,
    syncSearchWithActiveTab,
    closeSearchPanel,
    clearAllSearchHighlights,
    updateSearchStatus
  }
}
