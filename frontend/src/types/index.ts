export type Severity = 'RED' | 'ORANGE' | 'YELLOW' | 'GREEN' | 'BLUE' | 'UNKNOWN'
export type Language = 'en' | 'ur' | 'ar'

export interface ConversationMessage {
  id: string
  speaker: 'patient' | 'ai_nurse'
  original_text: string
  translated_text?: string
  detected_language?: string
  created_at: string
  timestamp_seconds?: number
}

export interface ClinicalFact {
  fact_key: string
  fact_value: string
  status: string
  confidence?: number
  source: string
  evidence_text?: string
  is_contradicted?: boolean
}

export interface VitalSigns {
  temperature?: number
  pulse?: number
  spo2?: number
  systolic_bp?: number
  diastolic_bp?: number
  respiratory_rate?: number
  avpu?: string
  source: string
}

export interface TriageResult {
  id?: string
  ai_recommendation: Severity
  clinician_decision?: Severity
  is_override: boolean
  override_reason?: string
  reviewed_by?: string
  status: string
  triggered_rules: TriggeredRule[]
  rules_version: string
  created_at?: string
}

export interface TriggeredRule {
  rule_id: string
  rule_description: string
  evidence_ids: string[]
}

export interface QueueEntry {
  patient_id: string
  visit_number: string
  session_id: string
  colour: Severity
  severity_label: string
  priority: number
  target_minutes: number
  remaining_seconds: number
  arrived_at: string
  session_status: string
  triage_status: string
  is_override: boolean
}

export interface AuthState {
  token: string | null
  role: string | null
  username: string | null
}
