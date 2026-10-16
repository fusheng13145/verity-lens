import { useQuery } from '@tanstack/react-query'
import { getFailureLedger } from '../api'
import type { FailureEntry } from '../types'

const CATEGORY_COLORS: Record<string, string> = {
  EXEC: 'bg-sky-100 text-sky-700 dark:bg-sky-900 dark:text-sky-200',
  DATA: 'bg-violet-100 text-violet-700 dark:bg-violet-900 dark:text-violet-200',
  METH: 'bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-200',
  HYP: 'bg-teal-100 text-teal-700 dark:bg-teal-900 dark:text-teal-200',
  EPIS: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-200',
}

export default function FailureLedger({ projectId }: { projectId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['ledger', projectId],
    queryFn: () => getFailureLedger(projectId),
    retry: false,
  })

  const entries: FailureEntry[] = data?.entries ?? []

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold text-zinc-800 dark:text-zinc-100">失败登记簿</h2>
      <p className="mt-1 text-xs text-zinc-500">
        失败经 `vl loop` / API 登记后驱动回流闭环（批准人与决策留痕）。
      </p>

      {isLoading && <p className="mt-3 text-sm text-zinc-500">加载中…</p>}
      {error && <p className="mt-3 text-sm text-zinc-400">暂无登记簿（docs/failure_ledger.json 不存在）</p>}

      {!isLoading && !error && entries.length === 0 && (
        <p className="mt-3 text-sm text-zinc-400">暂无失败条目。</p>
      )}

      <ul className="mt-3 space-y-2">
        {entries.map((e) => (
          <li
            key={e.id}
            className="rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-700"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                {e.id}
              </span>
              <span
                className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                  CATEGORY_COLORS[e.classification?.category] ?? 'bg-zinc-100 text-zinc-600'
                }`}
              >
                {e.classification?.category}/{e.classification?.code}
              </span>
              <span className="text-xs text-zinc-500">
                实验 {e.experiment_id} · 阶段 {e.phase}
              </span>
              <span className="ml-auto text-xs text-zinc-500">
                {e.decision?.type}
                {e.decision?.approved_by ? ` · 批准人 ${e.decision.approved_by}` : ' · 待批准'}
              </span>
            </div>
            {e.lesson && (
              <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">教训：{e.lesson}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
