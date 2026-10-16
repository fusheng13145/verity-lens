import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { getDoiMetrics, verifyDoiMetrics } from '../api'

const TARGET = 0.95

export default function DoiCard({ projectId }: { projectId: string }) {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['doi', projectId],
    queryFn: () => getDoiMetrics(projectId),
  })
  const refresh = useMutation({
    mutationFn: (online: boolean) => verifyDoiMetrics(projectId, online),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['doi', projectId] }),
  })

  if (isLoading) return <CardShell title="DOI 可验证率"><p className="text-sm text-zinc-500">加载中…</p></CardShell>
  if (error || !data)
    return (
      <CardShell title="DOI 可验证率">
        <p className="text-sm text-rose-600">度量读取失败（项目不存在或 API 未启动）</p>
      </CardShell>
    )

  const pct = Math.round(data.verification_rate * 100)
  const ok = data.verification_rate >= TARGET

  return (
    <CardShell
      title="DOI 可验证率"
      action={
        <div className="flex gap-2">
          <button
            className="rounded bg-zinc-200 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-300 disabled:opacity-50 dark:bg-zinc-700 dark:text-zinc-200"
            onClick={() => refresh.mutate(false)}
            disabled={refresh.isPending}
          >
            离线复算
          </button>
          <button
            className="rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            onClick={() => refresh.mutate(true)}
            disabled={refresh.isPending}
          >
            联网校验
          </button>
        </div>
      }
    >
      <div className="flex items-end gap-2">
        <span className={`text-3xl font-bold ${ok ? 'text-emerald-600' : 'text-amber-600'}`}>
          {pct}%
        </span>
        <span className="text-xs text-zinc-500">目标 ≥{Math.round(TARGET * 100)}%</span>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded bg-zinc-200 dark:bg-zinc-700">
        <div
          className={`h-full ${ok ? 'bg-emerald-500' : 'bg-amber-500'}`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-xs text-zinc-600 dark:text-zinc-300">
        <div><dt className="text-zinc-400">DOI 总数</dt><dd className="text-base font-semibold">{data.total}</dd></div>
        <div><dt className="text-zinc-400">格式合法</dt><dd className="text-base font-semibold">{data.valid_format}</dd></div>
        <div>
          <dt className="text-zinc-400">{data.online ? '已验证' : '联网已验证'}</dt>
          <dd className="text-base font-semibold">{data.online ? data.verified : '—'}</dd>
        </div>
      </dl>
      <p className="mt-2 text-xs text-zinc-400">
        度量时间 {data.checked_at ? new Date(data.checked_at).toLocaleString() : '—'}
        {data.online ? '（联网 Crossref）' : '（离线格式校验）'}
      </p>
    </CardShell>
  )
}

function CardShell({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-zinc-800 dark:text-zinc-100">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}
