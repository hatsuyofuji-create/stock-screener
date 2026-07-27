import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, Holding } from '../api'

export default function PortfolioPage() {
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [div, setDiv] = useState<Awaited<ReturnType<typeof api.diversification>> | null>(null)
  const [form, setForm] = useState({ company_code: '', buy_price: '', shares: '', buy_date: '', confidence: '3' })
  const [error, setError] = useState('')

  const load = () => {
    api.holdings().then(setHoldings).catch((e) => setError(String(e)))
    api.diversification().then(setDiv).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const add = async () => {
    setError('')
    try {
      await api.addHolding({
        company_code: form.company_code,
        buy_price: form.buy_price ? Number(form.buy_price) : null,
        shares: form.shares ? Number(form.shares) : null,
        buy_date: form.buy_date || null,
        confidence: form.confidence ? Number(form.confidence) : null,
      })
      setForm({ company_code: '', buy_price: '', shares: '', buy_date: '', confidence: '3' })
      load()
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">ポートフォリオ管理</h1>
      <p className="text-sm text-slate-500 mb-4">
        判断基準は常に「適正株価」。購入価格や含み益に惑わされない設計です（仕様書 4.8）。
      </p>
      {error && <div className="text-red-600 text-sm mb-3">{error}</div>}

      <div className="grid md:grid-cols-3 gap-6">
        <section className="md:col-span-2 bg-white rounded shadow p-4">
          <h2 className="font-bold mb-2">保有銘柄（目安 5〜10）</h2>
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-left">
              <tr>
                <th className="px-2 py-1">コード</th>
                <th className="px-2 py-1">買値</th>
                <th className="px-2 py-1">株数</th>
                <th className="px-2 py-1">取得日</th>
                <th className="px-2 py-1">自信度</th>
                <th className="px-2 py-1"></th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h) => (
                <tr key={h.id} className="border-t">
                  <td className="px-2 py-1">
                    <Link to={`/company/${h.company_code}`} className="text-blue-600">{h.company_code}</Link>
                  </td>
                  <td className="px-2 py-1">{h.buy_price ?? '—'}</td>
                  <td className="px-2 py-1">{h.shares ?? '—'}</td>
                  <td className="px-2 py-1">{h.buy_date ?? '—'}</td>
                  <td className="px-2 py-1">{h.confidence ?? '—'}</td>
                  <td className="px-2 py-1">
                    <button className="text-red-500 text-xs"
                      onClick={() => api.deleteHolding(h.id).then(load)}>削除</button>
                  </td>
                </tr>
              ))}
              {holdings.length === 0 && (
                <tr><td colSpan={6} className="px-2 py-4 text-center text-slate-400">保有なし</td></tr>
              )}
            </tbody>
          </table>

          <div className="mt-4 border-t pt-3 grid grid-cols-2 md:grid-cols-5 gap-2 text-sm items-end">
            <L label="コード"><input className="border rounded px-2 py-1 w-full" value={form.company_code}
              onChange={(e) => setForm({ ...form, company_code: e.target.value })} /></L>
            <L label="買値"><input className="border rounded px-2 py-1 w-full" value={form.buy_price}
              onChange={(e) => setForm({ ...form, buy_price: e.target.value })} /></L>
            <L label="株数"><input className="border rounded px-2 py-1 w-full" value={form.shares}
              onChange={(e) => setForm({ ...form, shares: e.target.value })} /></L>
            <L label="取得日"><input type="date" className="border rounded px-2 py-1 w-full" value={form.buy_date}
              onChange={(e) => setForm({ ...form, buy_date: e.target.value })} /></L>
            <L label="自信度1-5"><input type="number" min={1} max={5} className="border rounded px-2 py-1 w-full" value={form.confidence}
              onChange={(e) => setForm({ ...form, confidence: e.target.value })} /></L>
          </div>
          <button onClick={add} disabled={!form.company_code}
            className="mt-2 bg-slate-800 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50">
            保有を追加
          </button>
        </section>

        <section className="bg-white rounded shadow p-4">
          <h2 className="font-bold mb-2">分散チェック</h2>
          {div ? (
            <div className="text-sm">
              <div>保有数：<b>{div.count}</b></div>
              <div className="mt-2 text-xs text-slate-500">業種内訳</div>
              <ul className="text-sm">
                {Object.entries(div.sector_counts).map(([s, c]) => (
                  <li key={s} className="flex justify-between"><span>{s}</span><span>{c}</span></li>
                ))}
              </ul>
              {div.warnings.length > 0 && (
                <ul className="mt-3 text-red-600 text-xs list-disc pl-4">
                  {div.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
              {div.warnings.length === 0 && div.count > 0 && (
                <div className="mt-3 text-green-600 text-xs">分散は良好です。</div>
              )}
            </div>
          ) : <p className="text-sm text-slate-400">—</p>}
        </section>
      </div>
    </div>
  )
}

function L({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-500">{label}</span>
      {children}
    </label>
  )
}
