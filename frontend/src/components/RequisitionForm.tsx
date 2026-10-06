import { useState, FormEvent, ReactNode } from 'react'
import { parseJdFile } from '../api/jobs'
import type { JDFormFields, JobPosting, SkillGroup } from '../types'
import { MAX_RESUME_MB } from '../types'
import Button from './ui/Button'
import SkillGroupsEditor from './SkillGroupsEditor'
import './RequisitionForm.css'

/** Form values are kept as strings (what the inputs hold) and converted on
 *  submit -- except skill_groups, edited by SkillGroupsEditor. */
export interface RequisitionFormValues {
  title: string
  locations: string
  budget_min: string
  budget_max: string
  experience_min: string
  experience_max: string
  max_notice_days: string
  skill_groups: SkillGroup[]
  related_titles: string
  raw_text: string
}

type TextField = Exclude<keyof RequisitionFormValues, 'skill_groups'>

export interface RequisitionSubmit {
  title: string
  locations: string[]
  budget_min: number
  budget_max: number
  experience_min: number
  experience_max: number
  max_notice_days: number
  required_skills: string[]
  skill_groups: SkillGroup[]
  related_titles: string[]
  raw_text: string
  /** set when a JD file was uploaded in this form */
  jd_upload_token: string | null
  /** structured requirements read from the JD (incl. nice-to-have skills) */
  requirements: Record<string, unknown> | null
}

const EMPTY: RequisitionFormValues = {
  title: '', locations: '', budget_min: '', budget_max: '',
  experience_min: '', experience_max: '', max_notice_days: '45',
  skill_groups: [{ name: 'Must-have skills', type: 'must', skills: [], synonyms: [] }],
  related_titles: '', raw_text: '',
}

const copyGroups = (groups: SkillGroup[]): SkillGroup[] =>
  groups.map((g) => ({ ...g, skills: [...g.skills], synonyms: [...(g.synonyms || [])] }))

const MAX_JD_MB = MAX_RESUME_MB // same 4MB limit as resumes

export function valuesFromJob(job: JobPosting): RequisitionFormValues {
  return {
    title: job.title,
    locations: job.locations.join(', '),
    budget_min: String(job.budget_min ?? ''),
    budget_max: String(job.budget_max ?? ''),
    experience_min: String(job.experience_min ?? ''),
    experience_max: String(job.experience_max ?? ''),
    max_notice_days: String(job.max_notice_days ?? ''),
    skill_groups: copyGroups(job.skill_groups || []),
    related_titles: (job.related_titles || []).join(', '),
    raw_text: job.raw_text || '',
  }
}

/** Overlays the values the AI found in a JD on top of `base`; anything the
 *  JD didn't state keeps the base value. */
export function mergeJdFields(base: RequisitionFormValues, f: JDFormFields, rawText?: string): RequisitionFormValues {
  const num = (v: number | null, fallback: string) => (v === null || v === undefined ? fallback : String(v))
  return {
    title: f.title || base.title,
    locations: f.locations.length ? f.locations.join(', ') : base.locations,
    budget_min: num(f.budget_min, base.budget_min),
    budget_max: num(f.budget_max, base.budget_max),
    experience_min: num(f.experience_min, base.experience_min),
    experience_max: num(f.experience_max, base.experience_max),
    max_notice_days: num(f.max_notice_days, base.max_notice_days),
    skill_groups: f.skill_groups && f.skill_groups.length ? copyGroups(f.skill_groups) : base.skill_groups,
    related_titles: f.related_titles && f.related_titles.length ? f.related_titles.join(', ') : base.related_titles,
    raw_text: rawText && rawText.trim() ? rawText.trim() : base.raw_text,
  }
}

function jdFileProblem(file: File): string | null {
  const name = file.name.toLowerCase()
  if (name.endsWith('.doc')) return 'Old Word format (.doc) is not supported. Save it as .docx or PDF'
  if (!name.endsWith('.pdf') && !name.endsWith('.docx')) return 'Upload the JD as PDF or Word (.docx)'
  if (file.size === 0) return 'File is empty'
  if (file.size > MAX_JD_MB * 1024 * 1024) return `File is ${(file.size / (1024 * 1024)).toFixed(1)}MB; the limit is ${MAX_JD_MB}MB`
  return null
}

function formatLakh(v: string): string | null {
  const n = Number(v)
  if (!v || Number.isNaN(n) || n <= 0) return null
  return `₹${(n / 100000).toFixed(n % 100000 === 0 ? 0 : 1)}L`
}

interface RequisitionFormProps {
  initialValues?: RequisitionFormValues
  /** field keys to highlight as "not found in JD, please fill" */
  initialMissing?: string[]
  /** show the "Upload JD file" box (new requisitions) */
  allowJdUpload?: boolean
  /** extra banner shown above the fields */
  notice?: ReactNode
  submitLabel: string
  loading?: boolean
  error?: string | null
  onSubmit: (data: RequisitionSubmit) => void
  onCancel?: () => void
}

/**
 * Requisition (JD) form. With `allowJdUpload`, HR can upload the JD as
 * PDF/Word: the AI reads it and fills every field it can find; fields the
 * JD didn't state stay empty and are highlighted. Nothing is saved until
 * HR clicks the submit button.
 */
export default function RequisitionForm({
  initialValues, initialMissing = [], allowJdUpload = false, notice,
  submitLabel, loading = false, error, onSubmit, onCancel,
}: RequisitionFormProps) {
  const [values, setValues] = useState<RequisitionFormValues>(initialValues || EMPTY)
  const [missing, setMissing] = useState<Set<string>>(new Set(initialMissing))
  const [formError, setFormError] = useState<string | null>(null)

  const [jdReading, setJdReading] = useState(false)
  const [jdFileName, setJdFileName] = useState<string | null>(null)
  const [jdToken, setJdToken] = useState<string | null>(null)
  const [requirements, setRequirements] = useState<Record<string, unknown> | null>(null)
  const [jdMessage, setJdMessage] = useState<{ tone: 'ok' | 'warn' | 'bad'; text: string } | null>(null)
  const [jdInputKey, setJdInputKey] = useState(0)

  function set(key: TextField, value: string) {
    setValues((v) => ({ ...v, [key]: value }))
  }

  async function handleJdFile(file: File | undefined) {
    if (!file) return
    const problem = jdFileProblem(file)
    if (problem) {
      setJdMessage({ tone: 'bad', text: `${file.name}: ${problem}` })
      setJdInputKey((k) => k + 1)
      return
    }
    setJdReading(true)
    setJdMessage(null)
    try {
      const result = await parseJdFile(file)
      setJdFileName(result.file_name)
      setJdToken(result.upload_token)
      if (result.error) {
        setMissing(new Set())
        setJdMessage({ tone: 'warn', text: `${result.error}. The file will still be attached to this requisition.` })
        if (result.raw_text) set('raw_text', result.raw_text.trim())
        return
      }
      setValues((v) => mergeJdFields(v, result.fields, result.raw_text))
      setRequirements(result.requirements)
      setMissing(new Set(result.missing))
      setJdMessage({
        tone: result.missing.length ? 'warn' : 'ok',
        text: result.missing.length
          ? `Filled from ${result.file_name}. ${result.missing.length} field${result.missing.length === 1 ? ' was' : 's were'} not in the JD and ${result.missing.length === 1 ? 'is' : 'are'} highlighted. Please fill ${result.missing.length === 1 ? 'it' : 'them'} and check everything before saving.`
          : `Filled from ${result.file_name}. Please check every field before saving.`,
      })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setJdMessage({ tone: 'bad', text: typeof detail === 'string' ? detail : 'Could not upload the JD file. Fill the form manually or try again.' })
      setJdInputKey((k) => k + 1)
    } finally {
      setJdReading(false)
    }
  }

  function removeJd() {
    setJdToken(null)
    setJdFileName(null)
    setRequirements(null)
    setJdMessage(null)
    setMissing(new Set())
    setJdInputKey((k) => k + 1)
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const list = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean)
    const groups = values.skill_groups
      .map((g) => ({ ...g, name: g.name.trim() || g.skills[0] || '' }))
      .filter((g) => g.skills.length > 0)
    const mustSkills = groups.filter((g) => g.type === 'must').flatMap((g) => g.skills)
    if (mustSkills.length === 0) {
      setFormError('Add at least one must-have skill group.')
      setMissing((m) => new Set([...m, 'required_skills']))
      return
    }
    setFormError(null)
    onSubmit({
      title: values.title.trim(),
      locations: list(values.locations),
      budget_min: Number(values.budget_min),
      budget_max: Number(values.budget_max),
      experience_min: Number(values.experience_min),
      experience_max: Number(values.experience_max),
      max_notice_days: Number(values.max_notice_days),
      required_skills: Array.from(new Set(mustSkills)),
      skill_groups: groups,
      related_titles: list(values.related_titles),
      raw_text: values.raw_text,
      jd_upload_token: jdToken,
      requirements,
    })
  }

  // A field is highlighted while it's listed as missing AND still empty.
  const isMissing = (key: TextField) => missing.has(key) && !values[key].trim()
  const fieldClass = (key: TextField) => `field${isMissing(key) ? ' field-missing' : ''}`
  const missingHint = (key: TextField) =>
    isMissing(key) ? <span className="field-missing-hint">Not found in JD, please fill</span> : null

  return (
    <form className="jd-form requisition-form" onSubmit={handleSubmit}>
      {allowJdUpload && (
        <div className="jd-upload-box">
          <div className="jd-upload-head">
            <strong>Upload JD (optional)</strong>
            <span className="muted"> PDF or Word (.docx), max {MAX_JD_MB}MB. The form below is filled in automatically.</span>
          </div>
          {jdFileName ? (
            <div className="row">
              <span>📄 <strong>{jdFileName}</strong> will be attached</span>
              <button type="button" className="link-button muted" onClick={removeJd} disabled={jdReading}>Remove</button>
            </div>
          ) : (
            <input
              key={jdInputKey}
              type="file"
              accept=".pdf,.docx"
              disabled={jdReading}
              onChange={(e) => void handleJdFile(e.target.files?.[0])}
            />
          )}
          {jdReading && (
            <p className="muted jd-reading"><span className="spinner" aria-hidden="true" /> Reading the JD with AI… this takes about 5–15 seconds.</p>
          )}
          {jdMessage && <p className={`jd-message jd-message-${jdMessage.tone}`} role="status">{jdMessage.text}</p>}
        </div>
      )}

      {notice}

      <fieldset disabled={jdReading} className="requisition-fields">
        <div className={fieldClass('title')}>
          <label>Role title {missingHint('title')}</label>
          <input value={values.title} onChange={(e) => set('title', e.target.value)} required />
        </div>
        <div className={fieldClass('locations')}>
          <label>Locations (comma separated) {missingHint('locations')}</label>
          <input value={values.locations} onChange={(e) => set('locations', e.target.value)} placeholder="Mumbai, Remote" />
        </div>
        <div className="row">
          <div className={fieldClass('budget_min')}>
            <label>Budget min (₹ per year) {missingHint('budget_min')}</label>
            <input type="number" min={0} value={values.budget_min} onChange={(e) => set('budget_min', e.target.value)} required />
            {formatLakh(values.budget_min) && <span className="muted field-help">{formatLakh(values.budget_min)}</span>}
          </div>
          <div className={fieldClass('budget_max')}>
            <label>Budget max (₹ per year) {missingHint('budget_max')}</label>
            <input type="number" min={0} value={values.budget_max} onChange={(e) => set('budget_max', e.target.value)} required />
            {formatLakh(values.budget_max) && <span className="muted field-help">{formatLakh(values.budget_max)}</span>}
          </div>
        </div>
        <div className="row">
          <div className={fieldClass('experience_min')}>
            <label>Experience min (yrs) {missingHint('experience_min')}</label>
            <input type="number" min={0} step="0.5" value={values.experience_min} onChange={(e) => set('experience_min', e.target.value)} required />
          </div>
          <div className={fieldClass('experience_max')}>
            <label>Experience max (yrs) {missingHint('experience_max')}</label>
            <input type="number" min={0} step="0.5" value={values.experience_max} onChange={(e) => set('experience_max', e.target.value)} required />
          </div>
        </div>
        <div className={fieldClass('max_notice_days')}>
          <label>Max notice period (days) {missingHint('max_notice_days')}</label>
          <input type="number" min={0} value={values.max_notice_days} onChange={(e) => set('max_notice_days', e.target.value)} required />
        </div>
        <div className="field">
          <label>
            Skills used for scoring
            {missing.has('required_skills') && !values.skill_groups.some((g) => g.type === 'must' && g.skills.length)
              && <span className="field-missing-hint">Not found in JD, please fill</span>}
          </label>
          <SkillGroupsEditor
            groups={values.skill_groups}
            onChange={(skill_groups) => setValues((v) => ({ ...v, skill_groups }))}
            showMissing={missing.has('required_skills')}
          />
        </div>
        <div className="field">
          <label>Related job titles (comma separated, optional)</label>
          <input
            value={values.related_titles}
            onChange={(e) => set('related_titles', e.target.value)}
            placeholder="Data Analyst, BI Developer"
          />
          <span className="muted field-help">Candidates currently in one of these roles get full marks for role relevance.</span>
        </div>
        <div className="field">
          <label>Job description text</label>
          <textarea rows={allowJdUpload && values.raw_text ? 6 : 3} value={values.raw_text} onChange={(e) => set('raw_text', e.target.value)} />
        </div>
      </fieldset>

      {(formError || error) && <p className="error-text" role="alert">{formError || error}</p>}
      <div className="row">
        <Button type="submit" loading={loading} disabled={jdReading}>{submitLabel}</Button>
        {onCancel && <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  )
}
