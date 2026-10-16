export type Phase = 'literature' | 'question' | 'experiment' | 'analysis' | 'writing'

export interface GateInfo {
  ok: boolean
  hitl_required: boolean
  missing: string[]
}

export interface PhasesResponse {
  current_phase: string
  facts: Record<string, unknown>
  gates: Record<string, GateInfo>
}

export interface Approval {
  approved_by: string | null
  approved_at: string | null
  note: string | null
}

export interface ProjectInfo {
  project_id: string
  current_phase?: string
  approvals?: Record<string, Approval>
  metrics?: {
    doi_verification?: DoiMetric
  }
  [key: string]: unknown
}

export interface DoiMetric {
  total: number
  unique: number
  valid_format: number
  verified: number
  unverifiable: number
  verification_rate: number
  online: boolean
  checked_at: string
}

export interface FailureEntry {
  id: string
  experiment_id: string
  hypothesis_id: string
  phase: string
  classification: {
    category: string
    code: string
    confidence: number
  }
  decision: {
    type: string
    approved_by?: string | null
  }
  lesson?: string | null
  tags?: string[]
}

export interface FailureLedger {
  entries?: FailureEntry[]
}
