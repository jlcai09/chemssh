import assert from 'node:assert/strict'
import {
  isPathInsideWorkspace,
  sanitizeClientPreferencesForWorkspace,
  sanitizeTerminalTabs
} from '../src/api/workspaceScope'
import type { CanvasTerminalTabBinding, ClientPreferences } from '../src/types/canvasBoard'

assert.equal(isPathInsideWorkspace('/data/user/app/file.txt', '/data/user/app'), true)
assert.equal(isPathInsideWorkspace('/data/user/application/file.txt', '/data/user/app'), false)
assert.equal(isPathInsideWorkspace('/data/user/app', '/data/user/app/'), true)

assert.equal(isPathInsideWorkspace('/data/user/app/file.txt', '/'), true)
assert.equal(isPathInsideWorkspace('/', '/'), true)
assert.equal(isPathInsideWorkspace('D:\\Git\\chemssh', '/'), false)

assert.equal(isPathInsideWorkspace('D:\\Git\\chemssh\\README.md', 'D:\\Git\\chemssh'), true)
assert.equal(isPathInsideWorkspace('d:\\git\\CHEMSSH\\README.md', 'D:\\Git\\chemssh'), true)
assert.equal(isPathInsideWorkspace('E:\\Git\\chemssh\\README.md', 'D:\\Git\\chemssh'), false)
assert.equal(isPathInsideWorkspace('/data/user/app', 'D:\\Git\\chemssh'), false)

const tabs: CanvasTerminalTabBinding[] = [
  {
    tabId: 'local',
    title: 'Local',
    cwd: 'D:\\Git\\chemssh',
    syncMode: 'off',
    boundFileManagerId: null,
    active: true
  },
  {
    tabId: 'remote',
    title: 'Remote',
    cwd: '/data/user/app/jobs',
    syncMode: 'follow',
    boundFileManagerId: null,
    active: false
  }
]
assert.deepEqual(sanitizeTerminalTabs(tabs, '/data/user/app')?.map(tab => tab.tabId), ['remote'])
assert.equal(sanitizeTerminalTabs(tabs, '/data/user/app')?.[0]?.active, true)

const preferences: ClientPreferences = {
  version: 1,
  logs: { tailLines: 80 },
  workspace: { currentPath: 'D:\\Git\\chemssh', showHiddenFiles: true },
  terminal: { tabs }
}
const sanitized = sanitizeClientPreferencesForWorkspace(preferences, '/data/user/app')
assert.equal(sanitized.logs?.tailLines, 80)
assert.equal(sanitized.workspace?.currentPath, '/data/user/app')
assert.deepEqual(sanitized.terminal?.tabs?.map(tab => tab.tabId), ['remote'])
