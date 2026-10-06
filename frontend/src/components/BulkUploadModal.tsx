import { useEffect, useRef, useState } from 'react'
import {
  checkDuplicateResume, uploadResumeBatch, uploadCandidateResume, updateCandidateClassification,
  getIngestionStatus, reprocessCandidates, checkFingerprints,
} from '../api/candidates'
import { startAssessment } from '../api/assessments'
import { MAX_RESUME_MB } from '../types'
import type { DuplicateMatch, IngestionStatusRow, UploadBatchResult } from '../types'
import { splitResumeFiles, formatFileSize, fileFingerprint, InvalidResumeFile } from '../utils/resumeFiles'
import Button from './ui/Button'
import './BulkUploadModal.css'

/** Files per upload request. Small batches mean one bad file or a network
 *  blip only affects a handful of files, and progress updates often. */
const BATCH_SIZE = 10
/** Parallel duplicate checks (each one reads the file server-side). */
const CHECK_CONCURRENCY = 4
const POLL_MS = 3000
const IN_PROGRESS = ['queued', 'extracting', 'embedding']
const DUP_SKIP_REASON = 'Duplicate, skipped by you'

type Phase = 'precheck' | 'checking' | 'duplicates' | 'uploading' | 'processing' | 'done'

type RowState = 'pending' | 'uploaded' | 'replaced' | 'skipped' | 'failed'
interface FileRow {
  file: File
  state: RowState
  reason?: string
  candidateId?: string
}

type DupDecision = { type: 'replace'; candidateId: string } | { type: 'save' } | { type: 'skip' }
interface DupItem {
  file: File
  matches: DuplicateMatch[]
}

interface BulkUploadModalProps {
  files: File[]
  /** Upload against a job: every new candidate also gets a Pending Screening entry in that pipeline. */
  jobId?: string
  /** Pin every resume to this sector (skips AI sector detection). */
  sector?: string
  onClose: () => void
  /** Called whenever new candidates were created/changed, so the page can refresh its lists. */
  onChanged: () => void
}

function errorReason(err: any): string {
  if (!err?.response) return 'Network error: server not reachable'
  const status = err.response.status
  if (status === 413) return 'Batch too large for the server'
  const detail = err.response.data?.detail
  if (typeof detail === 'string') return detail
  return `Server error (${status})`
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/**
 * Popup that runs a whole bulk resume upload with live progress:
 *   1. pre-check   -- images, files over the size limit, wrong types: skip them or cancel
 *   2. duplicates  -- one check per file, then a decision per duplicate (with "apply to all")
 *   3. upload      -- batches of 10; a bad file or failed batch never stops the rest
 *   4. processing  -- live AI status (queued / extracting / embedding / ready / failed)
 *   5. summary     -- what failed and why, retry buttons, CSV report
 */
export default function BulkUploadModal({ files, jobId, sector, onClose, onChanged }: BulkUploadModalProps) {
  const [phase, setPhase] = useState<Phase>('precheck')
  const [invalid, setInvalid] = useState<InvalidResumeFile[]>([])
  const [validFiles, setValidFiles] = useState<File[]>([])
  // Pre-check progress (reading each file to fingerprint it).
  const [prechecked, setPrechecked] = useState<number | null>(0)

  const [checked, setChecked] = useState(0)
  const skipChecksRef = useRef(false)

  const [dupQueue, setDupQueue] = useState<DupItem[]>([])
  const [dupIndex, setDupIndex] = useState(0)
  const [applyToAll, setApplyToAll] = useState(false)
  const dupDecisionsRef = useRef<Map<File, DupDecision>>(new Map())

  const [rows, setRows] = useState<FileRow[]>([])
  const stopRef = useRef(false)

  const [statuses, setStatuses] = useState<IngestionStatusRow[]>([])
  const [retrying, setRetrying] = useState(false)
  // Set when the popup is closed/unmounted, so in-flight async work stops
  // instead of carrying on into an upload nobody is watching.
  const closedRef = useRef(false)
  // React StrictMode (dev) mounts, unmounts and re-mounts every component
  // once -- so reset the flag on (re)mount, and start the pipeline only once.
  const startedRef = useRef(false)
  useEffect(() => {
    closedRef.current = false
    return () => { closedRef.current = true }
  }, [])

  // --- 1. pre-check (runs once on open) ---
  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    void runPrecheck()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** Type/size/image rules, then exact-copy detection by file fingerprint:
   *  a second copy inside this upload, or a file already in the system,
   *  is skipped before anything is sent (no duplicate, no AI cost). */
  async function runPrecheck() {
    const { valid, invalid: bad } = splitResumeFiles(files)
    const ruleFailures = bad.length
    setPrechecked(ruleFailures)
    const firstByHash = new Map<string, File>()
    const hashOf = new Map<File, string>()
    const unique: File[] = []
    for (let i = 0; i < valid.length; i++) {
      if (closedRef.current) return
      const file = valid[i]
      const hash = await fileFingerprint(file)
      if (hash) {
        const first = firstByHash.get(hash)
        if (first) {
          bad.push({ file, reason: `Exact copy of "${first.name}" in this upload` })
          setPrechecked(ruleFailures + i + 1)
          continue
        }
        firstByHash.set(hash, file)
        hashOf.set(file, hash)
      }
      unique.push(file)
      setPrechecked(ruleFailures + i + 1)
    }

    let finalValid = unique
    if (hashOf.size > 0) {
      try {
        const matches = await checkFingerprints([...hashOf.values()])
        const existing = new Map(matches.map((m) => [m.hash, m.name]))
        finalValid = []
        for (const file of unique) {
          const name = existing.get(hashOf.get(file) || '')
          if (name) bad.push({ file, reason: `Exact copy of a resume already on file (${name})` })
          else finalValid.push(file)
        }
      } catch {
        // check unavailable -- the server still rejects exact copies on upload
      }
    }
    if (closedRef.current) return
    setPrechecked(null)
    setValidFiles(finalValid)
    setInvalid(bad)
    if (bad.length === 0) void runDuplicateChecks(finalValid)
  }

  // Warn before closing the tab while files are still being sent.
  useEffect(() => {
    if (phase !== 'checking' && phase !== 'uploading') return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [phase])

  // --- 2. duplicate checks ---
  async function runDuplicateChecks(toCheck: File[]) {
    if (toCheck.length === 0) { setPhase('done'); return }
    setPhase('checking')
    setChecked(0)
    skipChecksRef.current = false
    const found: DupItem[] = []
    let next = 0
    async function worker() {
      while (next < toCheck.length && !skipChecksRef.current && !closedRef.current) {
        const file = toCheck[next++]
        try {
          const result = await checkDuplicateResume(file)
          if (result.checked && result.matches.length > 0) found.push({ file, matches: result.matches })
        } catch {
          // A failed check never blocks the upload -- the file is uploaded as new.
        }
        setChecked((c) => c + 1)
      }
    }
    await Promise.all(Array.from({ length: Math.min(CHECK_CONCURRENCY, toCheck.length) }, worker))
    if (closedRef.current) return

    if (found.length > 0) {
      // Keep the original file order so the recruiter sees them predictably.
      found.sort((a, b) => toCheck.indexOf(a.file) - toCheck.indexOf(b.file))
      dupDecisionsRef.current = new Map()
      setDupQueue(found)
      setDupIndex(0)
      setApplyToAll(false)
      setPhase('duplicates')
    } else {
      void runUpload(toCheck, [])
    }
  }

  function decideDuplicate(decision: DupDecision) {
    const decisions = dupDecisionsRef.current
    const current = dupQueue[dupIndex]
    decisions.set(current.file, decision)
    let nextIndex = dupIndex + 1
    if (applyToAll) {
      for (; nextIndex < dupQueue.length; nextIndex++) {
        const item = dupQueue[nextIndex]
        decisions.set(item.file, decision.type === 'replace'
          ? { type: 'replace', candidateId: item.matches[0].candidate_id }
          : decision)
      }
    }
    if (nextIndex < dupQueue.length) {
      setDupIndex(nextIndex)
      return
    }
    // All duplicates decided -> build the upload list.
    const toCreate: File[] = []
    const toReplace: { file: File; candidateId: string }[] = []
    const skipped: File[] = []
    for (const file of validFiles) {
      const d = decisions.get(file)
      if (!d || d.type === 'save') toCreate.push(file)
      else if (d.type === 'replace') toReplace.push({ file, candidateId: d.candidateId })
      else skipped.push(file)
    }
    void runUpload(toCreate, toReplace, skipped)
  }

  // --- 3. upload in batches ---
  async function runUpload(
    toCreate: File[],
    toReplace: { file: File; candidateId: string }[],
    userSkipped: File[] = [],
  ) {
    setPhase('uploading')
    stopRef.current = false
    const initial: FileRow[] = [
      ...toReplace.map(({ file }) => ({ file, state: 'pending' as RowState })),
      ...toCreate.map((file) => ({ file, state: 'pending' as RowState })),
      ...userSkipped.map((file) => ({ file, state: 'skipped' as RowState, reason: DUP_SKIP_REASON })),
    ]
    setRows(initial)
    const update = (file: File, patch: Partial<FileRow>) =>
      setRows((prev) => prev.map((r) => (r.file === file ? { ...r, ...patch } : r)))

    let changed = false

    for (const { file, candidateId } of toReplace) {
      if (stopRef.current) break
      try {
        await uploadCandidateResume(candidateId, file)
        if (sector) await updateCandidateClassification(candidateId, { sector })
        if (jobId) await startAssessment(candidateId, jobId)
        update(file, { state: 'replaced', candidateId })
        changed = true
      } catch (err) {
        update(file, { state: 'failed', reason: errorReason(err) })
      }
    }

    for (let i = 0; i < toCreate.length; i += BATCH_SIZE) {
      if (stopRef.current || closedRef.current) break
      const batch = toCreate.slice(i, i + BATCH_SIZE)
      let result: UploadBatchResult | null = null
      let lastErr: any = null
      for (let attempt = 0; attempt < 2 && !result; attempt++) {
        try {
          result = await uploadResumeBatch(batch, jobId, sector)
        } catch (err) {
          lastErr = err
          if (attempt === 0) await sleep(2000)
        }
      }
      if (!result) {
        const reason = errorReason(lastErr)
        batch.forEach((file) => update(file, { state: 'failed', reason }))
        continue
      }
      // Match results back to files: failures by filename, the rest in order.
      const failedNames = new Map<string, string[]>()
      result.failed.forEach((f) => failedNames.set(f.filename, [...(failedNames.get(f.filename) || []), f.reason]))
      let createdIdx = 0
      for (const file of batch) {
        const reasons = failedNames.get(file.name)
        if (reasons && reasons.length > 0) {
          update(file, { state: 'failed', reason: reasons.shift() })
        } else {
          const cand = result.created[createdIdx++]
          update(file, cand ? { state: 'uploaded', candidateId: cand.id } : { state: 'failed', reason: 'No response for this file' })
        }
      }
      if (result.created.length > 0) changed = true
    }

    if (stopRef.current) {
      setRows((prev) => prev.map((r) => (r.state === 'pending' ? { ...r, state: 'skipped', reason: 'Upload stopped by you' } : r)))
    }
    if (changed) onChanged()
    setPhase('processing')
  }

  // --- 4. processing: poll AI status for everything uploaded/replaced ---
  const uploadedIds = rows.filter((r) => r.candidateId && (r.state === 'uploaded' || r.state === 'replaced')).map((r) => r.candidateId!)
  const allSettled = statuses.length > 0 && uploadedIds.length > 0 &&
    statuses.every((s) => !IN_PROGRESS.includes(s.status) || s.stuck)

  useEffect(() => {
    if (phase !== 'processing') return
    if (uploadedIds.length === 0) { setPhase('done'); return }
    let cancelled = false
    async function poll() {
      try {
        const data = await getIngestionStatus(uploadedIds)
        if (!cancelled) setStatuses(data)
      } catch {
        // keep the last known statuses; next poll may succeed
      }
    }
    void poll()
    const timer = setInterval(poll, POLL_MS)
    return () => { cancelled = true; clearInterval(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, uploadedIds.join(',')])

  useEffect(() => {
    if (phase === 'processing' && allSettled) {
      setPhase('done')
      onChanged()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, allSettled])

  // --- retries ---
  async function retryFailedUploads() {
    const failedFiles = rows.filter((r) => r.state === 'failed').map((r) => r.file)
    const keep = rows.filter((r) => r.state !== 'failed')
    setStatuses([])
    await runUpload(failedFiles, [])
    // Put back the rows that were already done so the summary stays complete.
    setRows((prev) => [...keep, ...prev])
  }

  async function retryProcessing() {
    const ids = statuses.filter((s) => s.status === 'failed' || s.status === 'needs_review' || s.stuck).map((s) => s.id)
    if (ids.length === 0) return
    setRetrying(true)
    try {
      await reprocessCandidates(ids)
      setStatuses((prev) => prev.map((s) => (ids.includes(s.id) ? { ...s, status: 'queued', status_detail: '', stuck: false } : s)))
      setPhase('processing')
    } finally {
      setRetrying(false)
    }
  }

  function downloadReport() {
    const statusById = new Map(statuses.map((s) => [s.id, s]))
    const lines = [['File', 'Size', 'Upload result', 'Upload problem', 'AI status', 'AI problem']]
    invalid.forEach(({ file, reason }) => lines.push([file.name, formatFileSize(file.size), 'skipped (pre-check)', reason, '', '']))
    rows.forEach((r) => {
      const st = r.candidateId ? statusById.get(r.candidateId) : undefined
      lines.push([
        r.file.name, formatFileSize(r.file.size), r.state, r.reason || '',
        st ? (st.stuck ? 'stuck' : st.status) : '', st?.status_detail || '',
      ])
    })
    const csv = lines.map((l) => l.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `resume-upload-report-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  // --- derived counts ---
  const count = (state: RowState) => rows.filter((r) => r.state === state).length
  const isUserSkip = (r: FileRow) => r.state === 'skipped' && r.reason === DUP_SKIP_REASON
  const toSend = rows.filter((r) => !isUserSkip(r))
  const uploadTotal = toSend.length
  const sent = toSend.filter((r) => r.state !== 'pending').length
  const statusCount = (s: string) => statuses.filter((x) => x.status === s && !x.stuck).length
  const stuckCount = statuses.filter((s) => s.stuck).length
  const readyCount = statusCount('ready')
  const reviewCount = statusCount('needs_review')
  const aiFailedCount = statusCount('failed')
  const processedCount = readyCount + reviewCount + aiFailedCount + stuckCount
  const aiProblems = statuses.filter((s) => s.status === 'failed' || s.status === 'needs_review' || s.stuck)
  const uploadProblems = rows.filter((r) => r.state === 'failed' || r.state === 'skipped')

  const busy = phase === 'checking' || phase === 'uploading'

  function handleClose() {
    if (phase === 'uploading') {
      if (!window.confirm('Stop the upload? Files already sent are kept; the rest will be skipped.')) return
      stopRef.current = true
      return
    }
    if (phase === 'checking') { skipChecksRef.current = true; closedRef.current = true }
    onClose()
  }

  const pct = (n: number, d: number) => (d > 0 ? Math.round((n / d) * 100) : 0)

  return (
    <div className="modal-overlay" onClick={busy ? undefined : handleClose}>
      <div className="modal-panel modal-panel-wide bulk-upload-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Uploading {files.length} resume{files.length === 1 ? '' : 's'}</h2>
        <p className="muted bulk-upload-limits">PDF or Word (.docx) only, max {MAX_RESUME_MB}MB per file. Image files are not accepted.</p>

        <ol className="bulk-steps">
          {(['precheck', 'checking', 'uploading', 'processing', 'done'] as Phase[]).map((p, i) => {
            const order = ['precheck', 'checking', 'duplicates', 'uploading', 'processing', 'done']
            const cur = order.indexOf(phase)
            const me = order.indexOf(p)
            const labels = ['Check files', 'Duplicates', 'Upload', 'AI processing', 'Summary']
            return (
              <li key={p} className={me < cur ? 'bulk-step-done' : me === cur || (p === 'checking' && phase === 'duplicates') ? 'bulk-step-active' : ''}>
                {labels[i]}
              </li>
            )
          })}
        </ol>

        {/* 1. pre-check in progress */}
        {phase === 'precheck' && prechecked !== null && (
          <section>
            <ProgressBar value={pct(prechecked, files.length)} />
            <p className="muted">Checking files (type, size, exact copies)… {prechecked} / {files.length}</p>
          </section>
        )}

        {/* 1. pre-check problems */}
        {phase === 'precheck' && prechecked === null && invalid.length > 0 && (
          <section>
            <p className="bulk-warning">
              <strong>{invalid.length} file{invalid.length === 1 ? '' : 's'} can't be uploaded</strong> and will be skipped.
              {' '}{validFiles.length} file{validFiles.length === 1 ? ' is' : 's are'} fine.
            </p>
            <ul className="bulk-problem-list">
              {invalid.map(({ file, reason }, i) => (
                <li key={i}><strong>{file.name}</strong> <span className="muted">({formatFileSize(file.size)})</span><div className="muted">{reason}</div></li>
              ))}
            </ul>
            <div className="row-between bulk-actions">
              <Button variant="secondary" onClick={onClose}>Cancel upload</Button>
              <Button onClick={() => void runDuplicateChecks(validFiles)} disabled={validFiles.length === 0}>
                {validFiles.length === 0 ? 'Nothing left to upload' : `Skip ${invalid.length} and upload ${validFiles.length}`}
              </Button>
            </div>
          </section>
        )}

        {/* 2a. duplicate checks */}
        {phase === 'checking' && (
          <section>
            <ProgressBar value={pct(checked, validFiles.length)} />
            <p className="muted">Checking for candidates already on file… {checked} / {validFiles.length}</p>
            <Button variant="secondary" size="sm" onClick={() => { skipChecksRef.current = true }}>
              Skip duplicate check and upload now
            </Button>
          </section>
        )}

        {/* 2b. duplicate decisions */}
        {phase === 'duplicates' && dupQueue[dupIndex] && (
          <section>
            <p className="bulk-warning">
              Possible duplicate {dupIndex + 1} of {dupQueue.length}: <strong>{dupQueue[dupIndex].file.name}</strong> matches:
            </p>
            <ul className="bulk-problem-list">
              {dupQueue[dupIndex].matches.map((m) => (
                <li key={m.candidate_id} className="row-between">
                  <div>
                    <strong>{m.name}</strong>
                    <div className="muted">{m.email} · {m.phone || 'no phone'} · matched on {m.matched_on.join(' & ')}</div>
                  </div>
                  <Button size="sm" variant="secondary" onClick={() => decideDuplicate({ type: 'replace', candidateId: m.candidate_id })}>
                    Replace this one's resume
                  </Button>
                </li>
              ))}
            </ul>
            {dupQueue.length - dupIndex > 1 && (
              <label className="bulk-apply-all">
                <input type="checkbox" checked={applyToAll} onChange={(e) => setApplyToAll(e.target.checked)} />
                Apply my choice to the remaining {dupQueue.length - dupIndex - 1} duplicate{dupQueue.length - dupIndex - 1 === 1 ? '' : 's'}
              </label>
            )}
            <div className="row-between bulk-actions">
              <Button variant="secondary" onClick={() => decideDuplicate({ type: 'skip' })}>Skip this file</Button>
              <Button variant="secondary" onClick={() => decideDuplicate({ type: 'save' })}>Save anyway (keep both)</Button>
            </div>
          </section>
        )}

        {/* 3. upload progress */}
        {phase === 'uploading' && (
          <section>
            <ProgressBar value={pct(sent, uploadTotal)} />
            <p className="muted">Uploading… <strong>{sent}</strong> / {uploadTotal}</p>
            <Counts items={[
              ['Uploaded', count('uploaded') + count('replaced'), 'ok'],
              ['Failed', count('failed'), 'bad'],
              ['Skipped', count('skipped') + invalid.length, 'muted'],
            ]} />
            <p className="muted bulk-hint">Keep this tab open until the upload finishes. AI processing continues on the server after that.</p>
          </section>
        )}

        {/* 4/5. processing + summary */}
        {(phase === 'processing' || phase === 'done') && (
          <section>
            {uploadedIds.length > 0 && (
              <>
                <ProgressBar value={pct(processedCount, uploadedIds.length)} />
                <p className="muted">
                  {phase === 'processing' ? 'AI processing…' : 'AI processing finished:'} <strong>{processedCount}</strong> / {uploadedIds.length}
                </p>
                <Counts items={[
                  ['Queued', statusCount('queued'), 'muted'],
                  ['Extracting', statusCount('extracting'), 'muted'],
                  ['Embedding', statusCount('embedding'), 'muted'],
                  ['Ready', readyCount, 'ok'],
                  ['Needs review', reviewCount, 'warn'],
                  ['Failed', aiFailedCount, 'bad'],
                  ['Stuck', stuckCount, 'bad'],
                ]} />
                {stuckCount > 0 && (
                  <p className="error-text">Some resumes have not moved for over 15 minutes. Check that the Celery worker and Redis are running, then click Retry AI processing.</p>
                )}
              </>
            )}

            <div className="bulk-summary">
              <strong>Upload:</strong> {count('uploaded')} new, {count('replaced')} replaced,
              {' '}{count('failed')} failed, {count('skipped') + invalid.length} skipped
            </div>

            {(uploadProblems.length > 0 || invalid.length > 0) && (
              <details className="bulk-details" open={phase === 'done'}>
                <summary>Files not uploaded ({uploadProblems.length + invalid.length})</summary>
                <ul className="bulk-problem-list">
                  {invalid.map(({ file, reason }, i) => (
                    <li key={`inv${i}`}><strong>{file.name}</strong><div className="muted">{reason}</div></li>
                  ))}
                  {uploadProblems.map((r, i) => (
                    <li key={`up${i}`}><strong>{r.file.name}</strong><div className="muted">{r.reason || r.state}</div></li>
                  ))}
                </ul>
              </details>
            )}

            {aiProblems.length > 0 && (
              <details className="bulk-details" open={phase === 'done'}>
                <summary>AI processing problems ({aiProblems.length})</summary>
                <ul className="bulk-problem-list">
                  {aiProblems.map((s) => (
                    <li key={s.id}>
                      <strong>{s.name}</strong>
                      <div className="muted">
                        {s.stuck ? 'Stuck (no progress for 15+ min)' : s.status === 'needs_review' ? 'Needs review' : 'Failed'}
                        {s.status_detail ? `: ${s.status_detail}` : ''}
                      </div>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            <div className="row-between bulk-actions">
              <div className="row">
                {count('failed') > 0 && phase === 'done' && (
                  <Button variant="secondary" size="sm" onClick={() => void retryFailedUploads()}>
                    Retry failed uploads ({count('failed')})
                  </Button>
                )}
                {aiProblems.length > 0 && (
                  <Button variant="secondary" size="sm" loading={retrying} onClick={() => void retryProcessing()}>
                    Retry AI processing ({aiProblems.length})
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={downloadReport}>Download report (CSV)</Button>
              </div>
              <Button onClick={onClose}>{phase === 'processing' ? 'Close (keeps processing)' : 'Done'}</Button>
            </div>
          </section>
        )}

        {busy && (
          <div className="bulk-actions">
            <Button variant="secondary" size="sm" onClick={handleClose}>
              {phase === 'uploading' ? 'Stop upload' : 'Cancel'}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="bulk-progress" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className="bulk-progress-fill" style={{ width: `${value}%` }} />
    </div>
  )
}

function Counts({ items }: { items: [string, number, 'ok' | 'bad' | 'warn' | 'muted'][] }) {
  return (
    <div className="bulk-counts">
      {items.map(([label, n, tone]) => (
        <span key={label} className={`bulk-count bulk-count-${tone}${n === 0 ? ' bulk-count-zero' : ''}`}>
          {label} <strong>{n}</strong>
        </span>
      ))}
    </div>
  )
}
