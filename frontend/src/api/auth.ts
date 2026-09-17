import client from './client'
import type { User } from '../types'

export async function register(name: string, email: string, password: string): Promise<User> {
  const { data } = await client.post<User>('/auth/register', { name, email, password })
  return data
}

export async function login(email: string, password: string): Promise<string> {
  // The backend's /auth/login endpoint is an OAuth2 password flow, so it expects
  // form data with 'username' (used as email) + 'password', not JSON.
  const form = new URLSearchParams()
  form.append('username', email)
  form.append('password', password)

  const { data } = await client.post<{ access_token: string }>('/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return data.access_token
}

export async function getCurrentUser(): Promise<User> {
  const { data } = await client.get<User>('/auth/me')
  return data
}
