import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { approvePhase, getPhases, getProject } from '../api'
import type { ProjectInfo } from '../types'

const PHASES = ['literature', 'question', 'experiment', 'analysis', 'writing'] as const

export default function HitlPanel({ projectId }: { projectId: string }) {
  const qc = useQueryClient()
  const [approver, setApprover] = useState('')
  const phases = useQuery({ queryKey: ['phases', projectId], queryFn: () => getPhases(projectId) })
  const project = useQuery({ queryKey: ['project', projectId], queryFn: () => getProject(projectId) })

  const approve = useMutation({
    mutationFn: (phase: string) =>
      approvePhase(projectId, { phase, approved_by: approver || 'anonymous' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      qc.invalidateQueries({ queryKey: ['phases', projectId] })
    },
  })

  const gates = phases.data?.gates ?? {}
  const approvals: Record<string, { approved_by: string | null }> =
    (project.data as ProjectInfo | undefined)?.approvals ?? {}

  const pending = PHASES.filter((p) => gates[p] && gates[p].hitl_required && !approvals[p]?.approved_by)

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold text-zinc-800 dark:text-zinc-100">HITL 审批</h2>
      <p className="mt-1 text-xs text-zinc-500">
        需人工审批的阶段门禁在此批准；批准写入 RESEARCH.yaml（approvals[phase]）。
      </p>

      <div className="mt-3 flex items-center gap-2">
        <input
          className="w-40 rounded border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
          placeholder="审批人姓名"
          value={approver}
          onChange={(e) => setApprover(e.target.value)}
        />
        {approve.isError && (
          <span className="text-xs text-rose-600">审批失败：{(approve.error as Error).message}</span>
        )}
        {approve.isSuccess && !approve.isPending && (
          <span className="text-xs text-emerald-600">已记录审批</span>
        )}
      </div>

      <ul className="mt-4 space-y-2">
        {PHASES.map((p) => {
          const gate = gates[p]
          if (!gate) return null
          const approved = approvals[p]?.approved_by
          return (
            <li
              key={p}
              className="flex items-center justify-between rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-700"
            >
              <div>
                <span className="text-sm font-medium text-zinc-800 dark:text-zinc-100">{p}</span>
                {gate.hitl_required && (
                  <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900 dark:text-amber-200">
                    需 HITL
                  </span>
                )}
              </div>
              {approved ? (
                <span className="text-xs text-emerald-600">已批准：{approved}</span>
              ) : gate.hitl_required ? (
                <button
                  className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                  disabled={approve.isPending}
                  onClick={() => approve.mutate(p)}
                >
                  批准
                </button>
              ) : (
                <span className="text-xs text-zinc-400">无需审批</span>
              )}
            </li>
          )
        })}
      </ul>

      {pending.length === 0 && (
        <p className="mt-3 text-xs text-zinc-400">当前无待审批阶段。</p>
      )}
    </section>
  )
}
