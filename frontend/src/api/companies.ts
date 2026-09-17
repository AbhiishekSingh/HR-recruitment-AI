import client from './client'
import type { Company } from '../types'

export async function listCompanies(): Promise<Company[]> {
  const { data } = await client.get<Company[]>('/companies')
  return data
}

export async function createCompany(payload: {
  name: string; industry: string; contact_name: string; contact_email: string; tier: string
}): Promise<Company> {
  const { data } = await client.post<Company>('/companies', payload)
  return data
}
