import { uploadFile } from '../api/files'
import { requestBlob } from '../api/http'
import { t } from '../i18n'

export function useTerminalTransfer() {
  async function chooseTransferFiles(): Promise<File[]> {
    return new Promise(resolve => {
      const input = document.createElement('input')
      let settled = false
      input.type = 'file'
      input.multiple = true
      input.style.position = 'fixed'
      input.style.left = '-9999px'
      input.style.top = '-9999px'
      const cleanup = () => {
        input.removeEventListener('change', handleChange)
        input.removeEventListener('cancel', handleCancel)
        window.removeEventListener('focus', handleFocus)
        window.setTimeout(() => input.remove(), 0)
      }
      const settle = (files: File[]) => {
        if (settled) return
        settled = true
        cleanup()
        resolve(files)
      }
      const handleChange = () => {
        settle(Array.from(input.files ?? []))
      }
      const handleCancel = () => {
        settle([])
      }
      const handleFocus = () => {
        window.setTimeout(() => {
          if (!settled && (!input.files || input.files.length === 0)) settle([])
        }, 300)
      }
      input.addEventListener('change', handleChange)
      input.addEventListener('cancel', handleCancel)
      window.addEventListener('focus', handleFocus)
      document.body.appendChild(input)
      input.click()
    })
  }

  async function triggerTransferDownload(paths: string[]) {
    const query =
      paths.length === 1
        ? `/api/files/download?path=${encodeURIComponent(paths[0])}`
        : `/api/files/download-selection?${downloadSelectionQuery(paths)}`
    const response = await requestBlob(query)
    const url = URL.createObjectURL(response.blob)
    const link = document.createElement('a')
    link.href = url
    link.download =
      response.filename ??
      (paths.length === 1 ? pathBaseName(paths[0]) : 'chemssh-selection.zip')
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  function downloadSelectionQuery(paths: string[]) {
    const query = new URLSearchParams()
    for (const path of paths) query.append('path', path)
    return query.toString()
  }

  function pathBaseName(path: string) {
    const normalized = path.trim().replace(/[\\/]+$/, '')
    if (!normalized) return ''
    const parts = normalized.split(/[\\/]/).filter(Boolean)
    if (parts.length > 0) return parts[parts.length - 1]
    return normalized
  }

  interface TransferRequestMessage {
    transfer_id: string
    direction: 'upload' | 'download'
    cwd: string
    argv: string[]
    paths?: string[]
    error?: string
  }

  async function handleTransferRequest(
    message: TransferRequestMessage,
    writeln: (text: string) => void,
    sendResult: (payload: { transfer_id: string; success: boolean; message: string }) => void,
    uploadHandler?: (path: string, files: File[]) => Promise<void>
  ) {
    if (message.error) {
      writeln(`\r\n${t('terminal.transferFailed')}: ${message.error}`)
      sendResult({ transfer_id: message.transfer_id, success: false, message: message.error })
      return
    }

    try {
      if (message.direction === 'upload') {
        const files = await chooseTransferFiles()
        if (files.length === 0) {
          sendResult({
            transfer_id: message.transfer_id,
            success: false,
            message: t('terminal.transferCancelled')
          })
          return
        }

        writeln(`\r\n${t('terminal.transferUploading', { count: files.length })}`)
        if (uploadHandler) {
          await uploadHandler(message.cwd, files)
        } else {
          for (const file of files) {
            await uploadFile(message.cwd, file)
          }
        }
        sendResult({
          transfer_id: message.transfer_id,
          success: true,
          message: t('terminal.transferUploaded', { count: files.length })
        })
        return
      }

      const paths = message.paths ?? []
      if (paths.length === 0) {
        throw new Error(t('terminal.transferNoFiles'))
      }
      await triggerTransferDownload(paths)
      sendResult({
        transfer_id: message.transfer_id,
        success: true,
        message: t('terminal.transferDownloadStarted')
      })
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      writeln(`\r\n${t('terminal.transferFailed')}: ${detail}`)
      sendResult({ transfer_id: message.transfer_id, success: false, message: detail })
    }
  }

  return { handleTransferRequest, chooseTransferFiles, triggerTransferDownload }
}
