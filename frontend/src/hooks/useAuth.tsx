import React, { createContext, useContext, useState, useCallback } from 'react'
import type { AuthState } from '../types'

interface AuthContextType extends AuthState {
  loginUser: (token: string, role: string, username: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [auth, setAuth] = useState<AuthState>({
    token: localStorage.getItem('token'),
    role: localStorage.getItem('role'),
    username: localStorage.getItem('username'),
  })

  const loginUser = useCallback((token: string, role: string, username: string) => {
    localStorage.setItem('token', token)
    localStorage.setItem('role', role)
    localStorage.setItem('username', username)
    setAuth({ token, role, username })
  }, [])

  const logout = useCallback(() => {
    localStorage.clear()
    setAuth({ token: null, role: null, username: null })
  }, [])

  return (
    <AuthContext.Provider value={{ ...auth, loginUser, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
