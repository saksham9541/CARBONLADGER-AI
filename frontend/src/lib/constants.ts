/**
 * Application-wide constants.
 *
 * CORE ARCHITECTURAL RULE:
 * The frontend NEVER performs carbon arithmetic.
 * All emission factor lookups, unit conversions,
 * Scope 1/2/3 calculations, and GHG Protocol computations
 * run exclusively in the Python backend using validated,
 * versioned emission factor tables and Python Decimal.
 *
 * The frontend only DISPLAYS results returned by the API.
 */

export const APP_NAME = import.meta.env.VITE_APP_NAME || 'CarbonLedger AI'
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || '0.1.0'
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const SYSTEM_PRINCIPLES = {
  /** Carbon arithmetic runs only in the Python backend */
  NO_BROWSER_CARBON_ARITHMETIC: true,
  /** All emission factors must come from an approved, versioned backend register */
  EMISSION_FACTORS_SOURCE: 'backend-approved-register' as const,
  /** No extraction result auto-fills missing evidence */
  NO_SILENT_GAP_FILLING: true,
} as const

export const SCOPES = {
  SCOPE_1: 'Scope 1 — Direct emissions',
  SCOPE_2: 'Scope 2 — Purchased electricity',
  SCOPE_3: 'Scope 3 — Value chain emissions',
} as const

export const EVIDENCE_STATUS = {
  PENDING: 'pending',
  EXTRACTING: 'extracting',
  REVIEW: 'review',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  MISSING: 'missing_evidence',
} as const

export const FILE_TYPES = {
  PDF: 'application/pdf',
  JPEG: 'image/jpeg',
  PNG: 'image/png',
  WEBP: 'image/webp',
  XLSX: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  CSV: 'text/csv',
  MP3: 'audio/mpeg',
  WAV: 'audio/wav',
  M4A: 'audio/mp4',
} as const
