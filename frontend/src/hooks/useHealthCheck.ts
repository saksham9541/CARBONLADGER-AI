import { useState, useEffect } from 'react'
import { api } from '@/lib/api'

export interface HealthStatus {
  status: 'ok' | 'degraded' | 'error'
  version: string
  timestamp: string
  environment: string
  services: Record<string, 'ok' | 'degraded' | 'error' | 'unconfigured'>
}

export function useHealthCheck() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function check() {
      setLoading(true)
      setError(null)
      const result = await api.get<HealthStatus>('/api/health')
      if (!cancelled) {
        if (result.error) {
          setError(result.error)
        } else if (result.data) {
          setHealth(result.data)
        }
        setLoading(false)
      }
    }

    check()
    return () => { cancelled = true }
  }, [])

  return { health, loading, error }
}
