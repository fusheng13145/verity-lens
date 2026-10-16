import axios from 'axios'
import type { Approval, DoiMetric, FailureLedger, PhasesResponse, ProjectInfo } from './types'

const http = axios.create({ baseURL: '', timeout: 15_000 })

export async function getProject(id: string): Promise<ProjectInfo> {
  const r = await http.get<ProjectInfo>(`/api/projects/${id}`)
  return r.data
}

export async function getPhases(id: string): Promise<PhasesResponse> {
  const r = await http.get<PhasesResponse>(`/api/projects/${id}/phases`)
  return r.data
}

export async function approvePhase(
  id: string,
  body: { phase: string; approved_by: string; note?: string | null },
): Promise<{ status: string; phase: string; approved_by: string }> {
  const r = await http.post(`/api/projects/${id}/approve_phase`, body)
  return r.data
}

export async function getFailureLedger(id: string): Promise<FailureLedger> {
  const r = await http.get<FailureLedger>(`/api/projects/${id}/failure_ledger`)
  return r.data
}

export async function getDoiMetrics(id: string): Promise<DoiMetric> {
  const r = await http.get<DoiMetric>(`/api/projects/${id}/doi-metrics`)
  return r.data
}

export async function verifyDoiMetrics(id: string, online = false): Promise<DoiMetric> {
  const r = await http.post<DoiMetric>(`/api/projects/${id}/doi-metrics`, { online })
  return r.data
}

export type { Approval }
