import { MAX_RESUME_MB } from '../types'

export const RESUME_ACCEPT = '.pdf,.docx'
const ALLOWED = ['.pdf', '.docx']
const IMAGE = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff', '.heic']

export interface InvalidResumeFile {
  file: File
  reason: string
}

function extensionOf(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

export function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
  return `${Math.max(1, Math.round(bytes / 1024))}KB`
}

/** Same rules as the backend's _resume_file_problem() -- checked in the
 *  browser first so bad files are caught before anything is uploaded. */
export function resumeFileProblem(file: File): string | null {
  const ext = extensionOf(file.name)
  if (IMAGE.includes(ext)) return 'Image file, not a resume document. Convert it to PDF and upload again'
  if (ext === '.doc') return 'Old Word format (.doc) is not supported. Save it as .docx or PDF'
  if (!ALLOWED.includes(ext)) return `Unsupported file type (${ext || 'no extension'}). Only PDF and Word (.docx) are accepted`
  if (file.size === 0) return 'File is empty'
  if (file.size > MAX_RESUME_MB * 1024 * 1024) {
    return `File is ${formatFileSize(file.size)}; the limit is ${MAX_RESUME_MB}MB`
  }
  return null
}

export function splitResumeFiles(files: File[]): { valid: File[]; invalid: InvalidResumeFile[] } {
  const valid: File[] = []
  const invalid: InvalidResumeFile[] = []
  for (const file of files) {
    const reason = resumeFileProblem(file)
    if (reason) invalid.push({ file, reason })
    else valid.push(file)
  }
  return { valid, invalid }
}

/** SHA-256 of a file's bytes as hex, or null if the browser can't hash
 *  (crypto.subtle only exists on https/localhost -- the server still
 *  rejects exact copies itself in that case). */
export async function fileFingerprint(file: File): Promise<string | null> {
  try {
    if (!globalThis.crypto?.subtle) return null
    const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
    return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('')
  } catch {
    return null
  }
}
