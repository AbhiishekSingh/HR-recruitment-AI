import type { AIUsageReport } from '../types'
import client from './client'

export async function getFunnel(): Promise<Record<string, number>> {
  const { data } = await client.get('/analytics/funnel')
  return data
}

export async function getByRole(): Promise<Array<{ job_id: string; title: string; company: string; total: number; pending: number; screened: number }>> {
  const { data } = await client.get('/analytics/by-role')
  return data
}

/** Exact AI spend (tokens and cost per call), last `days` days. */
export async function getAiUsage(days = 30): Promise<AIUsageReport> {
  const { data } = await client.get<AIUsageReport>('/analytics/ai-usage', { params: { days } })
  return data
}
