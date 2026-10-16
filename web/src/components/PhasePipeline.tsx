import type { PhasesResponse } from '../types'

const PHASES: { key: string; label: string }[] = [
  { key: 'literature', label: '文献' },
  { key: 'question', label: '问题' },
  { key: 'experiment', label: '实验' },
  { key: 'analysis', label: '分析' },
  { key: 'writing', label: '写作' },
]

function statusOf(gate: PhasesResponse['gates'][string]) {
  if (gate.ok && !gate.hitl_required) return { text: '通过', cls: 'bg-emerald-600' }
  if (gate.hitl_required) return { text: '待人工审批', cls: 'bg-amber-500' }
  return { text: '未就绪', cls: 'bg-rose-600' }
}

export default function PhasePipeline({ data }: { data: PhasesResponse }) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
      <h2 className="mb-4 text-lg font-semibold text-zinc-800 dark:text-zinc-100">
        阶段看板 · 当前阶段
        <span className="ml-2 rounded bg-indigo-100 px-2 py-0.5 text-sm font-medium text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200">
          {data.current_phase}
        </span>
      </h2>
      <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {PHASES.map((p) => {
          const gate = data.gates[p.key]
          const st = statusOf(gate)
          const isCurrent = data.current_phase === p.key
          return (
            <li
              key={p.key}
              className={`rounded-lg border p-3 ${
                isCurrent
                  ? 'border-indigo-400 ring-2 ring-indigo-300 dark:border-indigo-500'
                  : 'border-zinc-200 dark:border-zinc-700'
              } bg-zinc-50 dark:bg-zinc-800`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-zinc-800 dark:text-zinc-100">{p.label}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs text-white ${st.cls}`}>
                  {st.text}
                </span>
              </div>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{p.key}</p>
              {!gate.ok && gate.missing.length > 0 && (
                <ul className="mt-2 list-disc pl-4 text-xs text-rose-600 dark:text-rose-400">
                  {gate.missing.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
