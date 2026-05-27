import { request } from './http'

export interface PluginPanel {
  id: string
  title: string
  icon?: string
  kind?: string
  singleton?: boolean
  accepts?: {
    extensions?: string[]
    filenames?: string[]
    preview_types?: string[]
  }
}

export interface PluginManifest {
  id: string
  name: string
  version?: string | null
  description?: string | null
  panels: PluginPanel[]
  file_manager?: Record<string, unknown>
  dependencies?: Record<string, unknown>
  active?: boolean
}

export interface PluginListResponse {
  plugins: PluginManifest[]
}

export interface PluginActivationResponse {
  id: string
  active: boolean
  asset_url: string
  api_base: string
  panels: PluginPanel[]
  file_manager?: Record<string, unknown>
}

export interface PluginDependencyStatus {
  plugin_id: string
  python: {
    mode: string
    manifest_mode?: string
    python?: string | null
    requirements?: string | null
    packages: { name: string; version?: string | null }[]
    missing: string[]
    satisfied: boolean
  }
}

export function listPlugins() {
  return request<PluginListResponse>('/api/plugins')
}

export function activatePlugin(pluginId: string) {
  return request<PluginActivationResponse>(`/api/plugins/${encodeURIComponent(pluginId)}/activate`, {
    method: 'POST',
    body: JSON.stringify({})
  })
}

export function deactivatePlugin(pluginId: string) {
  return request<PluginActivationResponse>(`/api/plugins/${encodeURIComponent(pluginId)}/deactivate`, {
    method: 'POST',
    body: JSON.stringify({})
  })
}

export function getPluginDependencyStatus(pluginId: string) {
  return request<PluginDependencyStatus>(`/api/plugins/${encodeURIComponent(pluginId)}/dependencies`)
}

export function installPluginDependencies(pluginId: string, mode?: 'host' | 'venv', venv?: string) {
  return request<PluginDependencyStatus>(`/api/plugins/${encodeURIComponent(pluginId)}/dependencies/install`, {
    method: 'POST',
    body: JSON.stringify({ mode, venv })
  })
}

export function configurePluginExternalPython(pluginId: string, python: string) {
  return request<PluginDependencyStatus>(`/api/plugins/${encodeURIComponent(pluginId)}/dependencies/external`, {
    method: 'POST',
    body: JSON.stringify({ python })
  })
}
