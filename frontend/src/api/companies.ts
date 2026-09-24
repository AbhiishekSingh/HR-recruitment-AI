import client from './client'
import type { Company } from '../types'

export async function listCompanies(): Promise<Company[]> {
  const { data } = await client.get<Company[]>('/companies')
  return data
}

export async function createCompany(payload: {
  name: string; industry: string; contact_name: string; contact_email: string
  gst_number: string; tier: string; document?: File | null
}): Promise<Company> {
  const formData = new FormData()
  formData.append('name', payload.name)
  formData.append('industry', payload.industry)
  formData.append('contact_name', payload.contact_name)
  formData.append('contact_email', payload.contact_email)
  formData.append('gst_number', payload.gst_number)
  formData.append('tier', payload.tier)
  if (payload.document) formData.append('document', payload.document)

  const { data } = await client.post<Company>('/companies', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** Fetches the company's uploaded document as an authenticated blob and
 *  opens/downloads it — same pattern as viewCandidateResume, needed
 *  because the endpoint requires the bearer token a plain <a href> won't send. */
export async function viewCompanyDocument(company: Company): Promise<void> {
  const { data } = await client.get(`/companies/${company.id}/document`, { responseType: 'blob' })
  const ext = company.document_path?.split('.').pop() || 'pdf'
  const filename = `${company.name.replace(/\s+/g, '_')}.${ext}`

  const blobUrl = window.URL.createObjectURL(data)
  if (ext.toLowerCase() === 'pdf') {
    window.open(blobUrl, '_blank')
  } else {
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
  }
}
