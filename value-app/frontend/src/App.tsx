import { Routes, Route, NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from './api'
import MatrixPage from './pages/MatrixPage'
import ScreeningPage from './pages/ScreeningPage'
import CompanyDetailPage from './pages/CompanyDetailPage'
import PortfolioPage from './pages/PortfolioPage'
import ExcelPage from './pages/ExcelPage'
import BusinessCyclePage from './pages/BusinessCyclePage'

const NAV = [
  { to: '/', label: '銘柄マトリクス', end: true },
  { to: '/screening', label: 'スクリーニング' },
  { to: '/portfolio', label: 'ポートフォリオ' },
  { to: '/business-cycle', label: '景気局面' },
  { to: '/excel', label: '予想Excel取込' },
]

function Disclaimer() {
  const [text, setText] = useState('')
  useEffect(() => {
    api.disclaimer().then((d) => setText(d.disclaimer)).catch(() => {})
  }, [])
  return (
    <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-xs px-4 py-2">
      ⚠️ {text || '本アプリは投資助言ツールではありません。投資判断は利用者自身の責任で行ってください。'}
    </div>
  )
}

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-slate-900 text-white">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-6">
          <span className="font-bold text-lg">バリュー投資アプリ</span>
          <span className="text-slate-400 text-xs">上原メソッド</span>
          <nav className="flex gap-1 ml-auto flex-wrap">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm ${
                    isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:bg-slate-800'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <Disclaimer />
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<MatrixPage />} />
          <Route path="/screening" element={<ScreeningPage />} />
          <Route path="/company/:code" element={<CompanyDetailPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/business-cycle" element={<BusinessCyclePage />} />
          <Route path="/excel" element={<ExcelPage />} />
        </Routes>
      </main>
      <footer className="text-center text-xs text-slate-400 py-4">
        価値（Fスコア）×価格（安全域）の2軸で判断 — 計算はすべてバックエンドで実施
      </footer>
    </div>
  )
}
