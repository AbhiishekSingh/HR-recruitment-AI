import client from './client'
import type { ShortlistRow, FollowUp, StageHistoryEntry } from '../types'

export interface ShortlistFilters {
  company_id?: string
  job_id?: string
  stage?: string
  /** Matches candidate name, email, phone or role (job title). */
  search?: string
  invoice?: '' | 'yes' | 'no'
  /** Range on Expected CTC (₹). */
  min_ctc?: number | null
  max_ctc?: number | null
}

export async function listShortlisted(filters: ShortlistFilters = {}): Promise<ShortlistRow[]> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  )
  const { data } = await client.get<ShortlistRow[]>('/tracking/shortlisted', { params })
  return data
}

export async function getTrackingRow(assessmentId: string): Promise<ShortlistRow> {
  const { data } = await client.get<ShortlistRow>(`/tracking/assessments/${assessmentId}`)
  return data
}

export interface TrackingUpdatePayload {
  stage?: string
  stage_note?: string
  submitted_to?: string
  submitted_on?: string | null
  offered_ctc?: number | null
  joining_date?: string | null
  invoice_raised?: boolean
  invoice_date?: string | null
}

export async function updateTracking(assessmentId: string, payload: TrackingUpdatePayload): Promise<ShortlistRow> {
  const { data } = await client.patch<ShortlistRow>(`/assessments/${assessmentId}/tracking`, payload)
  return data
}

export async function getStageHistory(assessmentId: string): Promise<StageHistoryEntry[]> {
  const { data } = await client.get<StageHistoryEntry[]>(`/assessments/${assessmentId}/stage-history`)
  return data
}

export async function listFollowUps(assessmentId: string): Promise<FollowUp[]> {
  const { data } = await client.get<FollowUp[]>(`/assessments/${assessmentId}/follow-ups`)
  return data
}

export async function listCandidateFollowUps(candidateId: string): Promise<FollowUp[]> {
  const { data } = await client.get<FollowUp[]>(`/candidates/${candidateId}/follow-ups`)
  return data
}

export async function createFollowUp(
  assessmentId: string,
  payload: { follow_up_type: string; scheduled_at: string; notes: string },
): Promise<FollowUp> {
  const { data } = await client.post<FollowUp>(`/assessments/${assessmentId}/follow-ups`, payload)
  return data
}

export async function updateFollowUp(
  followUpId: string,
  payload: { status?: string; outcome?: string; notes?: string; reschedule_to?: string },
): Promise<FollowUp> {
  const { data } = await client.patch<FollowUp>(`/follow-ups/${followUpId}`, payload)
  return data
}

export async function deleteFollowUp(followUpId: string): Promise<void> {
  await client.delete(`/follow-ups/${followUpId}`)
}

export async function getDueFollowUps(days = 7): Promise<FollowUp[]> {
  const { data } = await client.get<FollowUp[]>('/tracking/follow-ups/due', { params: { days } })
  return data
}

export async function getInvoiceStatus(): Promise<ShortlistRow[]> {
  const { data } = await client.get<ShortlistRow[]>('/tracking/invoice-status')
  return data
}

// --- small shared formatters (Indian locale, matching the ₹ used elsewhere) ---

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return '—'
  // Plain YYYY-MM-DD dates are parsed as local dates (not UTC) to avoid an
  // off-by-one day in timezones behind/ahead of UTC.
  const d = /^\d{4}-\d{2}-\d{2}$/.test(isoDate) ? new Date(`${isoDate}T00:00:00`) : new Date(isoDate)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function formatMoney(value: number | null | undefined): string {
  if (value == null) return '—'
  return `₹${value.toLocaleString('en-IN')}`
}

/** Combines <input type="date"> + <input type="time"> values (browser local
 *  time) into a UTC ISO string for the API. */
export function toIsoFromLocal(dateStr: string, timeStr: string): string {
  return new Date(`${dateStr}T${timeStr || '10:00'}`).toISOString()
}
