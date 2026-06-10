import { t, type MessageKey } from '../i18n'
import { ApiError } from './http'

type MessagePattern = {
  pattern: RegExp
  key: MessageKey
  params: (match: RegExpMatchArray) => Record<string, string>
}

const MESSAGE_PATTERNS: MessagePattern[] = [
  {
    pattern: /^([A-Za-z][\w.-]*) command was not found on this host$/,
    key: 'api.commandNotFound',
    params: match => ({ command: match[1] })
  },
  {
    pattern: /^([A-Za-z][\w.-]*) timed out$/,
    key: 'api.commandTimedOut',
    params: match => ({ command: match[1] })
  },
  {
    pattern: /^([A-Za-z][\w.-]*) failed$/,
    key: 'api.commandFailed',
    params: match => ({ command: match[1] })
  },
  {
    pattern: /^Cancelled job (.+)$/,
    key: 'api.jobCancelled',
    params: match => ({ id: match[1] })
  },
  {
    pattern: /^([A-Za-z][\w.-]*) requested for job (.+)$/,
    key: 'api.actionRequestedForJob',
    params: match => ({ action: match[1], id: match[2] })
  },
  {
    pattern: /^Submitted batch job\s+(.+)$/,
    key: 'api.submittedBatchJob',
    params: match => ({ id: match[1] })
  },
  {
    pattern: /^Workdir not found: (.+)$/,
    key: 'api.workdirNotFound',
    params: match => ({ path: match[1] })
  },
  {
    pattern: /^Script not found: (.+)$/,
    key: 'api.scriptNotFound',
    params: match => ({ path: match[1] })
  },
  {
    pattern: /^File not found: (.+)$/,
    key: 'api.fileNotFound',
    params: match => ({ path: match[1] })
  },
  {
    pattern: /^Directory not found: (.+)$/,
    key: 'api.directoryNotFound',
    params: match => ({ path: match[1] })
  },
  {
    pattern: /^Path not found: (.+)$/,
    key: 'api.pathNotFound',
    params: match => ({ path: match[1] })
  }
]

const ERROR_CODE_KEYS: Partial<Record<string, MessageKey>> = {
  SQUEUE_TIMEOUT: 'api.commandTimedOut',
  QSTAT_TIMEOUT: 'api.commandTimedOut'
}

const ERROR_CODE_COMMANDS: Partial<Record<string, string>> = {
  SQUEUE_TIMEOUT: 'squeue',
  QSTAT_TIMEOUT: 'qstat'
}

export function apiErrorMessage(error: unknown, fallbackKey: MessageKey) {
  if (error instanceof ApiError) {
    return localizeBackendMessage(error.message, fallbackKey, error.code)
  }
  if (error instanceof Error) return localizeBackendMessage(error.message, fallbackKey)
  return t(fallbackKey)
}

export function localizeBackendMessage(message: string | null | undefined, fallbackKey?: MessageKey, code?: string) {
  const rawMessage = message?.trim()
  if (code) {
    const key = ERROR_CODE_KEYS[code]
    if (key) {
      return t(key, { command: ERROR_CODE_COMMANDS[code] ?? code.toLowerCase() })
    }
  }
  if (!rawMessage) return fallbackKey ? t(fallbackKey) : ''

  for (const item of MESSAGE_PATTERNS) {
    const match = rawMessage.match(item.pattern)
    if (match) return t(item.key, item.params(match))
  }
  return rawMessage
}
