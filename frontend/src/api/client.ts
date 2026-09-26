import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// Attach JWT from localStorage
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export default api

// ── Auth ──────────────────────────────────────────────────────────────────────
export const login = (username: string, password: string) => {
  const form = new URLSearchParams({ username, password })
  return api.post('/auth/token', form, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
}

export const register = (data: { username: string; password: string; role?: string; full_name?: string }) =>
  api.post('/auth/register', data)

// ── Patients ──────────────────────────────────────────────────────────────────
export const registerPatient = (data: {
  age?: number; biological_sex?: string; preferred_language?: string;
  arrival_method?: string; pregnancy_status?: string;
}) => api.post('/patients/', data)

export const getPatient = (id: string) => api.get(`/patients/${id}`)
export const listPatients = () => api.get('/patients/')

// ── Conversations ─────────────────────────────────────────────────────────────
export const sendTextMessage = (session_id: string, text: string, language?: string) =>
  api.post('/conversations/message/text', { session_id, text, language })

export const sendAudioMessage = (session_id: string, audioBlob: Blob, language?: string) => {
  const form = new FormData()
  form.append('session_id', session_id)
  form.append('audio', audioBlob, 'recording.webm')
  if (language) form.append('language', language)
  return api.post('/conversations/message/audio', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const enterVitalSigns = (data: Record<string, unknown>) =>
  api.post('/conversations/vitals', data)

export const getTranscript = (session_id: string) =>
  api.get(`/conversations/${session_id}/transcript`)

export const reportInactivity = (session_id: string) =>
  api.post(`/conversations/${session_id}/inactivity-alert`)

// ── Triage ────────────────────────────────────────────────────────────────────
export const computeTriage = (session_id: string) =>
  api.post(`/triage/${session_id}/compute`)

export const confirmTriage = (triage_result_id: string, decision: string) =>
  api.post(`/triage/${triage_result_id}/confirm`, { decision })

export const overrideTriage = (triage_result_id: string, new_severity: string, override_reason: string) =>
  api.post(`/triage/${triage_result_id}/override`, { new_severity, override_reason })

export const startReassessment = (session_id: string) =>
  api.post(`/triage/${session_id}/reassess`)

export const getTriageHistory = (session_id: string) =>
  api.get(`/triage/${session_id}/history`)

// ── Staff ─────────────────────────────────────────────────────────────────────
export const getPatientQueue = () => api.get('/staff/queue')
export const getPatientFull = (session_id: string) => api.get(`/staff/patient/${session_id}/full`)
export const escalatePatient = (session_id: string) => api.post(`/staff/patient/${session_id}/escalate`)

// ── Audit ─────────────────────────────────────────────────────────────────────
export const getAuditTrail = (session_id: string) => api.get(`/audit/${session_id}`)
