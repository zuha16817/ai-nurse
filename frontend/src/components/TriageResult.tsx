import React from 'react'
import type { Severity, TriggeredRule } from '../types'

const COLOUR_LABELS: Record<Severity, string> = {
  RED: 'IMMEDIATE',
  ORANGE: 'VERY URGENT',
  YELLOW: 'URGENT',
  GREEN: 'STANDARD',
  BLUE: 'NON-URGENT',
  UNKNOWN: 'UNKNOWN',
}

const COLOUR_MINUTES: Record<Severity, string> = {
  RED: '0 minutes',
  ORANGE: '10 minutes',
  YELLOW: '60 minutes',
  GREEN: '120 minutes',
  BLUE: '240 minutes',
  UNKNOWN: 'Unknown',
}

interface TriageResultProps {
  colour: Severity
  triggeredRules?: TriggeredRule[]
  rulesVersion?: string
  isOverride?: boolean
  clinicianDecision?: Severity
  onConfirm?: () => void
  onOverride?: (newSeverity: Severity, reason: string) => void
  onReassess?: () => void
  readonly?: boolean
}

export const TriageResultPanel: React.FC<TriageResultProps> = ({
  colour, triggeredRules = [], rulesVersion, isOverride,
  clinicianDecision, onConfirm, onOverride, onReassess, readonly
}) => {
  const [overrideMode, setOverrideMode] = React.useState(false)
  const [newSeverity, setNewSeverity] = React.useState<Severity>('YELLOW')
  const [overrideReason, setOverrideReason] = React.useState('')

  const displayColour = clinicianDecision || colour

  return (
    <div className="card" style={{ marginTop: 20 }}>
      {/* Header - always says "AI TRIAGE RECOMMENDATION" not "FINAL TRIAGE" */}
      <div style={{ marginBottom: 16, textAlign: 'center' }}>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          {clinicianDecision ? 'FINAL CLINICIAN DECISION' : 'PRELIMINARY TRIAGE RECOMMENDATION'}
        </div>
        {isOverride && (
          <div style={{ color: '#f59e0b', fontSize: '0.75rem', marginTop: 2 }}>
            (Override - clinician changed from preliminary recommendation)
          </div>
        )}
      </div>

      {/* Big severity indicator */}
      <div style={{ textAlign: 'center', marginBottom: 20 }}>
        <div className={`severity-badge severity-${displayColour}`}
          style={{ fontSize: '2rem', padding: '16px 40px', display: 'inline-flex', borderRadius: 16 }}>
          <span>●</span>
          <span style={{ marginLeft: 12 }}>
            {displayColour} - {COLOUR_LABELS[displayColour]}
          </span>
        </div>
        <div style={{ marginTop: 8, color: 'var(--text-muted)' }}>
          Target assessment: <strong>{COLOUR_MINUTES[displayColour]}</strong>
        </div>
        {rulesVersion && (
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
            Rules version: {rulesVersion}
          </div>
        )}
      </div>

      {/* Evidence / triggered rules */}
      {triggeredRules.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontWeight: 600, marginBottom: 8, color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase' }}>
            Evidence Contributing to Assessment:
          </div>
          {triggeredRules.map(rule => (
            <div key={rule.rule_id} style={{
              display: 'flex', gap: 10, alignItems: 'flex-start',
              background: 'var(--surface2)', borderRadius: 8, padding: '10px 14px', marginBottom: 8
            }}>
              <span style={{ color: 'var(--green)', fontWeight: 700 }}>✓</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{rule.rule_description}</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Rule: {rule.rule_id}
                  {rule.evidence_ids?.length > 0 && ` · Evidence: ${rule.evidence_ids.join(', ')}`}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Clinician actions */}
      {!readonly && !clinicianDecision && (
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
          {!overrideMode ? (
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button className="btn-success" onClick={onConfirm}>
                ✓ Accept Recommendation
              </button>
              <button className="btn-warning" onClick={() => setOverrideMode(true)}>
                ✎ Change Severity
              </button>
              <button className="btn-secondary" onClick={onReassess}>
                ↺ Request Further Assessment
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontWeight: 600 }}>Override Triage Severity</div>
              <select value={newSeverity} onChange={e => setNewSeverity(e.target.value as Severity)}>
                {(['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE'] as Severity[]).map(s => (
                  <option key={s} value={s}>{s} - {COLOUR_LABELS[s]}</option>
                ))}
              </select>
              <textarea
                placeholder="Override reason (required)..."
                value={overrideReason}
                onChange={e => setOverrideReason(e.target.value)}
                rows={3}
              />
              <div style={{ display: 'flex', gap: 10 }}>
                <button className="btn-danger"
                  disabled={!overrideReason.trim()}
                  onClick={() => { onOverride?.(newSeverity, overrideReason); setOverrideMode(false) }}>
                  Confirm Override
                </button>
                <button className="btn-secondary" onClick={() => setOverrideMode(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
