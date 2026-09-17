import client from './client'

export async function getFunnel(): Promise<Record<string, number>> {
  const { data } = await client.get('/analytics/funnel')
  return data
}

export async function getByRole(): Promise<Array<{ job_id: string; title: string; company: string; total: number; pending: number; screened: number }>> {
  const { data } = await client.get('/analytics/by-role')
  return data
}
