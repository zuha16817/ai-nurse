import React, { useState, useEffect, useRef } from 'react'
import { getPatientQueue } from '../api/client'
import type { QueueEntry, Severity } from '../types'

const SEVERITY_RANK: Record<string, number> = { RED: 1, ORANGE: 2, YELLOW: 3, GREEN: 4, BLUE: 5, UNKNOWN: 6 }

export const CommandCenter: React.FC = () => {
  const [queue, setQueue] = useState<QueueEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterSeverity, setFilterSeverity] = useState<string>('ALL')
  // Spec §44 — highlight patients whose condition has deteriorated since the last poll.
  const [deterioratedIds, setDeterioratedIds] = useState<Set<string>>(new Set())
  const previousColours = useRef<Record<string, string>>({})

  const fetchQueue = async () => {
    try {
      const res = await getPatientQueue()
      const newQueue: QueueEntry[] = res.data
      const worsened = new Set<string>()
      for (const item of newQueue) {
        const prev = previousColours.current[item.session_id]
        if (prev && SEVERITY_RANK[item.colour] < SEVERITY_RANK[prev]) {
          worsened.add(item.session_id)
        }
      }
      previousColours.current = Object.fromEntries(newQueue.map(q => [q.session_id, q.colour]))
      setDeterioratedIds(worsened)
      setQueue(newQueue)
      setError(null)
    } catch (e: any) {
      setError(e.message || 'Failed to load ED patient queue')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchQueue()
    const interval = setInterval(fetchQueue, 5000) // Poll every 5 seconds
    return () => clearInterval(interval)
  }, [])

  const filteredQueue = filterSeverity === 'ALL'
    ? queue
    : queue.filter(q => q.colour === filterSeverity)

  const formatRemaining = (seconds: number) => {
    if (seconds <= 0) return '00:00 (Target Exceeded)'
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')} remaining`
  }

  return (
    <div className="page" style={{ maxWidth: 1200 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: '2rem', display: 'flex', alignItems: 'center', gap: 12 }}>
            <span>🚨 Emergency Department Triage Command Center</span>
          </h1>
          <p style={{ color: 'var(--text-muted)' }}>
            Real-time patient queue sorted by Severity → Clinical Target Time → Arrival State
          </p>
        </div>
        <button className="btn-secondary" onClick={fetchQueue}>↻ Refresh</button>
      </div>

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 24 }}>
        {(['RED', 'ORANGE', 'YELLOW', 'GREEN', 'BLUE'] as Severity[]).map(sev => {
          const count = queue.filter(q => q.colour === sev).length
          return (
            <div key={sev}
              className={`card severity-${sev}`}
              style={{ padding: 16, cursor: 'pointer', opacity: filterSeverity === 'ALL' || filterSeverity === sev ? 1 : 0.4 }}
              onClick={() => setFilterSeverity(filterSeverity === sev ? 'ALL' : sev)}>
              <div style={{ fontSize: '0.8rem', textTransform: 'uppercase', opacity: 0.9 }}>{sev}</div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800 }}>{count}</div>
              <div style={{ fontSize: '0.75rem', opacity: 0.8 }}>Patients</div>
            </div>
          )
        })}
      </div>

      {/* Queue table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>PATIENT QUEUE ({filteredQueue.length})</h3>
          {filterSeverity !== 'ALL' && (
            <button className="btn-secondary" style={{ padding: '4px 12px', fontSize: '0.8rem' }} onClick={() => setFilterSeverity('ALL')}>
              Clear Filter
            </button>
          )}
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading queue...</div>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--red)' }}>{error}</div>
        ) : filteredQueue.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No patients currently waiting in triage queue.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: 'var(--surface2)', fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                <th style={{ padding: '14px 20px' }}>Patient ID</th>
                <th style={{ padding: '14px 20px' }}>Urgency Level</th>
                <th style={{ padding: '14px 20px' }}>Clinical Target Time</th>
                <th style={{ padding: '14px 20px' }}>Session Status</th>
                <th style={{ padding: '14px 20px' }}>Triage Status</th>
                <th style={{ padding: '14px 20px' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredQueue.map(item => (
                <tr key={item.session_id} style={{
                  borderBottom: '1px solid var(--border)',
                  background: deterioratedIds.has(item.session_id) ? 'rgba(220,38,38,0.15)' : undefined,
                }}>
                  <td style={{ padding: '16px 20px', fontWeight: 700 }}>
                    {item.visit_number}
                  </td>
                  <td style={{ padding: '16px 20px' }}>
                    <span className={`severity-badge severity-${item.colour}`}>
                      {item.colour} — {item.severity_label}
                    </span>
                    {item.is_override && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--yellow)', marginLeft: 8 }} title="Clinician Overridden">
                        ✎ Override
                      </span>
                    )}
                    {deterioratedIds.has(item.session_id) && (
                      <span style={{ fontSize: '0.75rem', color: '#f87171', marginLeft: 8, fontWeight: 700 }} title="Condition has worsened since last check">
                        ▲ Deteriorating
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '16px 20px', fontFamily: 'monospace', fontWeight: 600, color: item.remaining_seconds === 0 ? 'var(--red)' : 'var(--text)' }}>
                    {formatRemaining(item.remaining_seconds)}
                  </td>
                  <td style={{ padding: '16px 20px', fontSize: '0.9rem' }}>
                    {item.session_status}
                  </td>
                  <td style={{ padding: '16px 20px', fontSize: '0.9rem' }}>
                    {item.triage_status}
                  </td>
                  <td style={{ padding: '16px 20px' }}>
                    <a href={`/nurse/${item.session_id}`} className="btn-primary" style={{ textDecoration: 'none', display: 'inline-block', padding: '6px 14px', fontSize: '0.85rem' }}>
                      Review Patient →
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
