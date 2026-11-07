/**
 * Typed API client for CarbonLedger AI.
 *
 * This module handles all HTTP communication with the FastAPI backend.
 * The frontend NEVER performs carbon arithmetic — all calculations,
 * unit conversions, and factor lookups happen server-side.
 */

import { API_BASE_URL } from './constants'

export interface ApiResponse<T> {
  data?: T
  error?: string
  status: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

async function request<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<ApiResponse<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    })
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      return {
        error: errorData.detail || `HTTP error ${response.status}`,
        status: response.status,
      }
    }
    const data: T = await response.json()
    return { data, status: response.status }
  } catch (err) {
    return {
      error: err instanceof Error ? err.message : 'Network error — is the backend running?',
      status: 0,
    }
  }
}

export const api = {
  get: <T>(endpoint: string, headers?: HeadersInit) =>
    request<T>(endpoint, { method: 'GET', headers }),

  post: <T>(endpoint: string, body: unknown, headers?: HeadersInit) =>
    request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(body),
      headers,
    }),

  put: <T>(endpoint: string, body: unknown) =>
    request<T>(endpoint, { method: 'PUT', body: JSON.stringify(body) }),

  patch: <T>(endpoint: string, body: unknown) =>
    request<T>(endpoint, { method: 'PATCH', body: JSON.stringify(body) }),

  delete: <T>(endpoint: string) =>
    request<T>(endpoint, { method: 'DELETE' }),

  /** Upload files using multipart/form-data */
  upload: <T>(endpoint: string, formData: FormData) =>
    request<T>(endpoint, { method: 'POST', body: formData, headers: {} }),
}
