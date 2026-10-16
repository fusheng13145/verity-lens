import { useQuery } from '@tanstack/react-query'
import { getPhases } from '../api'
import PhasePipeline from '../components/PhasePipeline'
import DoiCard from '../components/DoiCard'
import HitlPanel from '../components/HitlPanel'
import FailureLedger from '../components/FailureLedger'

export default function Dashboard({ projectId }: { projectId: string }) {
  const phases = useQuery({
    queryKey: ['phases', projectId],
    queryFn: () => getPhases(projectId),
    retry: false,
  })

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">
            verity-lens · 科研全流程看板
          </h1>
          <p className="text-sm text-zinc-500">
            项目 <span className="font-mono">{projectId}</span> · 数据来自 Headless API（:8000）
          </p>
        </div>
        <a
          href="/"
          className="rounded border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-100 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          切换项目
        </a>
      </header>

      {phases.isLoading && <p className="text-sm text-zinc-500">加载阶段门禁…</p>}
      {phases.isError && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300">
          无法加载项目「{projectId}」：后端未启动（<code>make api</code>）或项目不存在。
        </div>
      )}

      {phases.data && (
        <div className="space-y-6">
          <PhasePipeline data={phases.data} />
          <div className="grid gap-6 lg:grid-cols-2">
            <DoiCard projectId={projectId} />
            <HitlPanel projectId={projectId} />
          </div>
          <FailureLedger projectId={projectId} />
        </div>
      )}
    </div>
  )
}
