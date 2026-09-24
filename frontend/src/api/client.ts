import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
})

// Attach the JWT to every request once the user is logged in.
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// If a token expires/is invalid, bounce back to login rather than showing
// a confusing raw 401 in the UI. Login/register calls are excluded --
// those 401s are an expected "wrong password" response the form itself
// shows inline, not a session-expiry event. Without this check, a wrong
// password on the login page triggered this same redirect to '/login'
// (the page the person was already on), forcing a hard reload that wiped
// out the form's own error state right as it was about to render
// "Incorrect email or password" -- so a wrong password just looked like
// the page silently flickered with no feedback at all.
const AUTH_ENDPOINTS = ['/auth/login', '/auth/register']

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const url: string = error.config?.url || ''
    const isAuthEndpoint = AUTH_ENDPOINTS.some((path) => url.includes(path))
    if (error.response?.status === 401 && !isAuthEndpoint) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client
