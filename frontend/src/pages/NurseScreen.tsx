import React, { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { getPatientFull, confirmTriage, overrideTriage, startReassessment, enterVitalSigns, computeTriage, escalatePatient } from '../api/client'
import { TriageResultPanel } from '../components/TriageResult'
import type { Severity } from '../types'

const SEVERITY_RANK: Record<string, number> = { RED: 1, ORANGE: 2, YELLOW: 3, GREEN: 4, BLUE: 5, UNKNOWN: 6 }

export const NurseScreen: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'triage' | 'vitals' | 'transcript' | 'audit'>('triage')

  // Vitals form state
  const [vitals, setVitals] = useState({
    temperature: '',
    pulse: '',
    spo2: '',
    systolic_bp: '',
    diastolic_bp: '',
    respiratory_rate: '',
    avpu: '', // '' = not assessed. Never default to a real level: that would assert a finding nobody made.
    pain_score: '',
  })
  const [vitalsSubmitted, setVitalsSubmitted] = useState(false)
  const [deteriorationAlert, setDeteriorationAlert] = useState<string | null>(null)

  const loadData = async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const res = await getPatientFull(sessionId)
      setData(res.data)
    } catch (e: any) {
      setError(e.message || 'Failed to load patient record')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [sessionId])

  const handleConfirm = async () => {
    if (!data?.triage?.id) return
    try {
      await confirmTriage(data.triage.id, data.triage.ai_recommendation)
      await loadData()
    } catch (e: any) {
      alert('Error confirming triage: ' + e.message)
    }
  }

  const handleOverride = async (newSeverity: Severity, reason: string) => {
    if (!data?.triage?.id) return
    try {
      await overrideTriage(data.triage.id, newSeverity, reason)
      await loadData()
    } catch (e: any) {
      alert('Error overriding triage: ' + e.message)
    }
  }

  const handleEscalate = async () => {
    try {
      await escalatePatient(sessionId!)
      await loadData()
      alert('Patient escalated to clinical team.')
    } catch (e: any) {
      alert('Error escalating patient: ' + e.message)
    }
  }

  const handleReassess = async () => {
    try {
      const res = await startReassessment(sessionId!)
      alert('New assessment session created: ' + res.data.new_session_id)
      window.location.href = `/nurse/${res.data.new_session_id}`
    } catch (e: any) {
      alert('Reassessment error: ' + e.message)
    }
  }

  const handleRunTriage = async () => {
    try {
      await computeTriage(sessionId!)
      await loadData()
    } catch (e: any) {
      alert('Triage engine error: ' + e.message)
    }
  }

  const handleVitalsSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const previousColour: string | undefined = data?.triage?.ai_recommendation
    try {
      await enterVitalSigns({
        session_id: sessionId,
        temperature: vitals.temperature ? parseFloat(vitals.temperature) : null,
        pulse: vitals.pulse ? parseInt(vitals.pulse) : null,
        spo2: vitals.spo2 ? parseFloat(vitals.spo2) : null,
        systolic_bp: vitals.systolic_bp ? parseInt(vitals.systolic_bp) : null,
        diastolic_bp: vitals.diastolic_bp ? parseInt(vitals.diastolic_bp) : null,
        respiratory_rate: vitals.respiratory_rate ? parseInt(vitals.respiratory_rate) : null,
        avpu: vitals.avpu || null,
        pain_score: vitals.pain_score ? parseInt(vitals.pain_score) : null,
      })

      // Spec §44 - re-run the deterministic engine on the new observations. This
      // creates a NEW triage result row (re-triage, spec §20); it never overwrites
      // the previous one, so the full history stays intact.
      await computeTriage(sessionId!)
      const res = await getPatientFull(sessionId!)
      setData(res.data)

      const newColour: string | undefined = res.data?.triage?.ai_recommendation
      if (previousColour && newColour && SEVERITY_RANK[newColour] < SEVERITY_RANK[previousColour]) {
        setDeteriorationAlert(`⚠ Patient condition has changed: ${previousColour} → ${newColour}`)
      } else {
        setDeteriorationAlert(null)
      }

      setVitalsSubmitted(true)
      setTimeout(() => setVitalsSubmitted(false), 3000)
    } catch (e: any) {
      alert('Error submitting vitals: ' + e.message)
    }
  }

  if (loading) return <div className="page" style={{ padding: 40, textAlign: 'center' }}>Loading patient record...</div>
  if (error) return <div className="page" style={{ color: 'var(--red)', padding: 40 }}>Error: {error}</div>

  const patient = data?.patient
  const triage = data?.triage
  const facts = data?.clinical_facts || []
  const conversation = data?.conversation || []
  const auditTrail = data?.audit_trail || []
  const vitalSigns = data?.vital_signs

  return (
    <div className="page">
      {/* Header bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <a href="/command-center" style={{ color: '#3b82f6', textDecoration: 'none', fontSize: '0.9rem' }}>← Back to Command Center</a>
          <h1 style={{ fontSize: '1.8rem', marginTop: 4 }}>Patient Record: {patient?.visit_number || 'Unknown'}</h1>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Age: {patient?.age || 'N/A'} | Lang: {patient?.preferred_language?.toUpperCase() || 'EN'} | Session ID: {sessionId}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn-danger" onClick={handleEscalate}>
            🚨 Escalate
          </button>
          <button className="btn-secondary" onClick={handleReassess}>
            ↺ Start Reassessment
          </button>
        </div>
      </div>

      {deteriorationAlert && (
        <div style={{ background: '#7f1d1d', color: '#fecaca', padding: '12px 16px', borderRadius: 8, marginBottom: 16, fontWeight: 600 }}>
          {deteriorationAlert}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 10, borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {(['triage', 'vitals', 'transcript', 'audit'] as const).map(tab => (
          <button key={tab}
            className={activeTab === tab ? 'btn-primary' : 'btn-secondary'}
            style={{ borderRadius: '8px 8px 0 0', textTransform: 'capitalize' }}
            onClick={() => setActiveTab(tab)}>
            {tab === 'triage' ? 'Triage & Evidence' : tab === 'vitals' ? 'Vital Signs' : tab === 'transcript' ? 'Transcript' : 'Audit Log'}
          </button>
        ))}
      </div>

      {/* Tab 1: Triage & Evidence */}
      {activeTab === 'triage' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div>
            {triage && triage.ai_recommendation ? (
              <TriageResultPanel
                colour={triage.ai_recommendation}
                triggeredRules={triage.triggered_rules}
                rulesVersion={triage.rules_version}
                isOverride={triage.is_override}
                clinicianDecision={triage.clinician_decision}
                onConfirm={handleConfirm}
                onOverride={handleOverride}
                onReassess={handleReassess}
              />
            ) : (
              <div className="card" style={{ textAlign: 'center', padding: 40 }}>
                <p style={{ color: 'var(--text-muted)', marginBottom: 16 }}>No triage result calculated yet.</p>
                <button className="btn-primary" onClick={handleRunTriage}>
                  ⚙ Run Deterministic Triage Engine
                </button>
              </div>
            )}
          </div>

          <div>
            <div className="card">
              <h3 style={{ marginBottom: 14 }}>Extracted Clinical Facts</h3>
              {facts.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>No facts extracted yet.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {facts.map((f: any, idx: number) => (
                    <div key={idx} style={{ background: 'var(--surface2)', padding: 12, borderRadius: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                        <span>{f.fact_key}</span>
                        <span style={{ color: f.status === 'PRESENT' ? 'var(--green)' : 'var(--yellow)' }}>{f.fact_value} ({f.status})</span>
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
                        Source: {f.source} | Confidence: {((f.confidence || 0) * 100).toFixed(0)}%
                      </div>
                      {f.evidence_text && (
                        <div style={{ fontSize: '0.82rem', fontStyle: 'italic', marginTop: 4, color: '#93c5fd' }}>
                          "{f.evidence_text}"
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Vitals */}
      {activeTab === 'vitals' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div className="card">
            <h3>Enter Objective Measurements</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: 16 }}>
              Nurse/Clinician entries are tagged as OBJECTIVELY_MEASURED.
            </p>
            <form onSubmit={handleVitalsSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label style={{ fontSize: '0.85rem' }}>Temperature (°C)</label>
                <input type="number" step="0.1" value={vitals.temperature} onChange={e => setVitals({ ...vitals, temperature: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: '0.85rem' }}>Heart Rate (Pulse, bpm)</label>
                <input type="number" value={vitals.pulse} onChange={e => setVitals({ ...vitals, pulse: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: '0.85rem' }}>Oxygen Saturation (SpO2 %)</label>
                <input type="number" step="0.1" value={vitals.spo2} onChange={e => setVitals({ ...vitals, spo2: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: '0.85rem' }}>Blood Pressure (Systolic / Diastolic)</label>
                <div style={{ display: 'flex', gap: 10 }}>
                  <input type="number" placeholder="Systolic" value={vitals.systolic_bp} onChange={e => setVitals({ ...vitals, systolic_bp: e.target.value })} />
                  <input type="number" placeholder="Diastolic" value={vitals.diastolic_bp} onChange={e => setVitals({ ...vitals, diastolic_bp: e.target.value })} />
                </div>
              </div>
              <div>
                <label style={{ fontSize: '0.85rem' }}>Respiratory Rate (breaths/min)</label>
                <input type="number" value={vitals.respiratory_rate} onChange={e => setVitals({ ...vitals, respiratory_rate: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: '0.85rem' }}>Pain Score (0-10)</label>
                <input type="number" min="0" max="10" value={vitals.pain_score} onChange={e => setVitals({ ...vitals, pain_score: e.target.value })} />
              </div>
              <div>
                <label style={{ fontSize: '0.85rem' }}>Level of Consciousness (AVPU)</label>
                <select value={vitals.avpu} onChange={e => setVitals({ ...vitals, avpu: e.target.value })}>
                  <option value="">Not assessed</option>
                  <option value="Alert">Alert</option>
                  <option value="Voice">Voice</option>
                  <option value="Pain">Pain</option>
                  <option value="Unresponsive">Unresponsive</option>
                </select>
              </div>
              <button className="btn-primary" type="submit" style={{ marginTop: 8 }}>
                Save Vital Signs & Re-Run Engine
              </button>
              {vitalsSubmitted && <div style={{ color: 'var(--green)', fontSize: '0.85rem' }}>✓ Vital signs saved successfully!</div>}
            </form>
          </div>

          <div className="card">
            <h3>Current Vital Signs</h3>
            {vitalSigns ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>SpO2:</span> <strong>{vitalSigns.spo2 ? `${vitalSigns.spo2}%` : 'N/A'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>Heart Rate:</span> <strong>{vitalSigns.pulse ? `${vitalSigns.pulse} bpm` : 'N/A'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>Temperature:</span> <strong>{vitalSigns.temperature ? `${vitalSigns.temperature}°C` : 'N/A'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>Blood Pressure:</span> <strong>{vitalSigns.systolic_bp ? `${vitalSigns.systolic_bp} mmHg` : 'N/A'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span>Resp Rate:</span> <strong>{vitalSigns.respiratory_rate ? `${vitalSigns.respiratory_rate}/min` : 'N/A'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
                  <span>AVPU:</span> <strong>{vitalSigns.avpu || 'N/A'}</strong>
                </div>
              </div>
            ) : (
              <p style={{ color: 'var(--text-muted)', marginTop: 16 }}>No vital signs recorded yet.</p>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Transcript */}
      {activeTab === 'transcript' && (
        <div className="card">
          <h3>Full Conversation Transcript</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: 16 }}>
            Original statements are preserved intact as mandatory evidence.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {conversation.map((msg: any) => (
              <div key={msg.id} style={{
                background: msg.speaker === 'patient' ? 'var(--surface2)' : '#1e3a8a',
                padding: 14, borderRadius: 10, borderLeft: `4px solid ${msg.speaker === 'patient' ? '#3b82f6' : '#60a5fa'}`
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                  <span>{msg.speaker === 'patient' ? 'Patient' : 'Triage System'} ({msg.id})</span>
                  <span>{new Date(msg.created_at).toLocaleTimeString()}</span>
                </div>
                <div style={{ fontWeight: 600 }}>{msg.original_text}</div>
                {msg.translated_text && msg.translated_text !== msg.original_text && (
                  <div style={{ fontSize: '0.85rem', color: '#93c5fd', marginTop: 4 }}>
                    English Translation: "{msg.translated_text}"
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 4: Audit */}
      {activeTab === 'audit' && (
        <div className="card">
          <h3>Immutable Audit Trail</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: 16 }}>
            Complete provenance log tracking all system actions, clinician overrides, and engine rules.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {auditTrail.map((log: any, idx: number) => (
              <div key={idx} style={{ background: 'var(--surface2)', padding: 12, borderRadius: 8, fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                  <span style={{ color: '#60a5fa' }}>{log.action}</span>
                  <span style={{ color: 'var(--text-muted)' }}>{new Date(log.timestamp).toLocaleTimeString()}</span>
                </div>
                <div style={{ marginTop: 4 }}>Actor: {log.actor || 'system'}</div>
                {log.detail && (
                  <pre style={{ background: '#0f172a', padding: 8, borderRadius: 6, marginTop: 6, overflowX: 'auto', fontSize: '0.75rem' }}>
                    {JSON.stringify(log.detail, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
