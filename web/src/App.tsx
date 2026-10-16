import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import Dashboard from './pages/Dashboard'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 10_000 } },
})

function Home() {
  const navigate = useNavigate()
  const [pid, setPid] = useState(() => localStorage.getItem('vl.project') ?? '')
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-4">
      <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">verity-lens</h1>
      <p className="mt-1 text-sm text-zinc-500">输入项目 ID 进入阶段看板与 HITL 审批</p>
      <form
        className="mt-6 flex w-full gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          const id = pid.trim()
          if (!id) return
          localStorage.setItem('vl.project', id)
          navigate(`/project/${id}`)
        }}
      >
        <input
          className="flex-1 rounded border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
          placeholder="project_id（如 proj_test）"
          value={pid}
          onChange={(e) => setPid(e.target.value)}
        />
        <button
          type="submit"
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          打开
        </button>
      </form>
    </div>
  )
}

function ProjectRoute() {
  const { id = '' } = useParams()
  return id ? <Dashboard projectId={id} /> : <Home />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/project/:id" element={<ProjectRoute />} />
          <Route path="*" element={<Home />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
