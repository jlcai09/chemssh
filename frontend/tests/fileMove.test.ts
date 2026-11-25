import assert from 'node:assert/strict'
import { copyPaths, movePaths, type FileItem } from '../src/api/files'
import { prepareMoveEntries } from '../src/api/fileMove'

const items = [
  { name: 'vasp.script', path: '/workspace/vasp.script', type: 'file' },
  { name: 'case', path: '/workspace/case', type: 'directory' }
] as FileItem[]
const listing = {
  path: '/workspace',
  items: [...items, { ...items[0], name: 'vasp.script.new', path: '/workspace/vasp.script.new' }]
}
const calls: { url: string; body: any }[] = []
globalThis.fetch = async (input, init) => {
  const url = String(input)
  if (init?.method === 'POST') {
    calls.push({ url, body: JSON.parse(String(init.body)) })
    return new Response(JSON.stringify({ success: true, message: 'OK' }))
  }
  return new Response(JSON.stringify(listing))
}

let prompts = 0
const prepared = await prepareMoveEntries(items, {
  targetPath: '/workspace',
  promptConflict: async () => {
    prompts += 1
    return { action: 'suffix', applyAll: true }
  }
})
assert.equal(prompts, 1)
assert.equal(prepared.cancelled, false)
assert.deepEqual(prepared.entries, [
  { path: '/workspace/vasp.script', targetName: 'vasp.script.new.new', overwrite: false },
  { path: '/workspace/case', targetName: 'case.new', overwrite: false }
])

for (const operation of [copyPaths, movePaths]) {
  await operation(items.map(item => item.path), '/workspace', prepared.entries)
  const call = calls.at(-1)!
  assert.equal(call.url, operation === copyPaths ? '/api/files/copy' : '/api/files/move')
  assert.deepEqual(call.body, {
    paths: items.map(item => item.path),
    target_directory: '/workspace',
    items: [
      { path: '/workspace/vasp.script', target_name: 'vasp.script.new.new', overwrite: false },
      { path: '/workspace/case', target_name: 'case.new', overwrite: false }
    ]
  })
  await operation(['/workspace/vasp.script'], '/workspace')
  assert.deepEqual(calls.at(-1)!.body.items, [])
  await operation(['/workspace/vasp.script'], '/workspace', [
    { path: '/workspace/vasp.script', overwrite: true }
  ])
  assert.deepEqual(calls.at(-1)!.body.items, [{ path: '/workspace/vasp.script', overwrite: true }])
}

console.log('File copy/move suffix preparation and request serialization passed')
