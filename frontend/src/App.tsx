import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { PatientScreen } from './pages/PatientScreen'
import { NurseScreen } from './pages/NurseScreen'
import { CommandCenter } from './pages/CommandCenter'
import { LoginScreen } from './pages/LoginScreen'

// Clinical staff screens require a logged-in nurse/admin — the backend already
// enforces this on every request, but redirecting client-side avoids a confusing
// "flash of 401s" for anyone who reaches these URLs without signing in first.
const RequireStaffAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token } = useAuth()
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

// Navigation Bar
const Navbar: React.FC = () => {
  const { token, username, logout } = useAuth()

  return (
    <nav style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', padding: '12px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <a href="/" style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--text)', textDecoration: 'none' }}>
          🏥 AI Nurse System
        </a>
        <a href="/" style={{ color: 'var(--text-muted)', textDecoration: 'none', fontSize: '0.9rem' }}>Patient Kiosk</a>
        <a href="/command-center" style={{ color: 'var(--text-muted)', textDecoration: 'none', fontSize: '0.9rem' }}>Command Center</a>
      </div>

      <div>
        {token ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Staff: <strong>{username}</strong></span>
            <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '0.85rem' }} onClick={logout}>Sign Out</button>
          </div>
        ) : (
          <a href="/login" className="btn-secondary" style={{ textDecoration: 'none', padding: '6px 14px', fontSize: '0.85rem' }}>Staff Login</a>
        )}
      </div>
    </nav>
  )
}

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Navbar />
        <Routes>
          <Route path="/" element={<PatientScreen />} />
          <Route path="/login" element={<LoginScreen />} />
          <Route path="/nurse/:sessionId" element={<RequireStaffAuth><NurseScreen /></RequireStaffAuth>} />
          <Route path="/command-center" element={<RequireStaffAuth><CommandCenter /></RequireStaffAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
