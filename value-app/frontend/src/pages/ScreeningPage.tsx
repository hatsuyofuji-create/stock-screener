import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ScreenHit, ThresholdCriteria } from '../api'

const PCT = (v: number | null | undefined) => (typeof v === 'number' ? (v * 100).toFixed(1) + '%' : '—')
const NUM = (v: number | null | undefined) => (typeof v === 'number' ? v.toFixed(2) : '—')

export default function ScreeningPage() {
  const [mode, setMode] = useState<'threshold' | 'magic'>('threshold')
  const [criteria, setCriteria] = useState<ThresholdCriteria>({
    net_cash_required: false,
    fcf_positive: false,
    price_change_3y_negative: false,
    fscore_min: 7,
  })
  const [hits, setHits] = useState<ScreenHit[]>([])
  const [count, setCount] = useState(0)
  const [error, setError] = useState('')

  // ヒット件数をリアルタイム表示（仕様書 4.5）
  useEffect(() => {
    if (mode !== 'threshold') return
    api.screenThreshold(criteria)
      .then((r) => { setCount(r.count); setHits(r.hits) })
      .catch((e) => setError(String(e)))
  }, [criteria, mode])

  useEffect(() => {
    if (mode !== 'magic') return
    api.screenMagic(30)
      .then((r) => { setCount(r.count); setHits(r.results) })
      .catch((e) => setError(String(e)))
  }, [mode])

  const set = (patch: Partial<ThresholdCriteria>) => setCriteria((c) => ({ ...c, ...patch }))
  const numOrNull = (v: string) => (v === '' ? null : Number(v))

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-bold">スクリーニング</h1>
        <div className="flex gap-1 ml-auto text-sm">
          <button onClick={() => setMode('threshold')}
            className={`px-3 py-1.5 rounded ${mode === 'threshold' ? 'bg-slate-800 text-white' : 'bg-slate-200'}`}>
            モードA：閾値フィルター
          </button>
          <button onClick={() => setMode('magic')}
            className={`px-3 py-1.5 rounded ${mode === 'magic' ? 'bg-slate-800 text-white' : 'bg-slate-200'}`}>
            モードB：魔法の公式
          </button>
        </div>
      </div>

      {error && <div className="text-red-600 text-sm mb-3">{error}</div>}

      {mode === 'threshold' && (
        <div className="bg-white rounded shadow p-4 mb-4 grid md:grid-cols-2 gap-3 text-sm">
          <Field label="配当利回り ≥（例 0.03）">
            <input type="number" step="0.01" className="border rounded px-2 py-1 w-32"
              onChange={(e) => set({ dividend_yield_min: numOrNull(e.target.value) })} />
          </Field>
          <Field label="自己資本比率 ≥（例 0.5）">
            <input type="number" step="0.01" className="border rounded px-2 py-1 w-32"
              onChange={(e) => set({ equity_ratio_min: numOrNull(e.target.value) })} />
          </Field>
          <Field label="ROE ≥（例 0.15）">
            <input type="number" step="0.01" className="border rounded px-2 py-1 w-32"
              onChange={(e) => set({ roe_min: numOrNull(e.target.value) })} />
          </Field>
          <Field label="時価総額 ≤（円）">
            <input type="number" className="border rounded px-2 py-1 w-40"
              onChange={(e) => set({ market_cap_max: numOrNull(e.target.value) })} />
          </Field>
          <Field label="Fスコア ≥">
            <input type="number" defaultValue={7} className="border rounded px-2 py-1 w-20"
              onChange={(e) => set({ fscore_min: numOrNull(e.target.value) })} />
          </Field>
          <div className="flex flex-col gap-1">
            <Check label="純有利子負債 < 0（ネットキャッシュ）"
              onChange={(v) => set({ net_cash_required: v })} />
            <Check label="FCF（営業CF+投資CF）> 0"
              onChange={(v) => set({ fcf_positive: v })} />
            <Check label="株価3年変化率 < 0（逆張り）"
              onChange={(v) => set({ price_change_3y_negative: v })} />
          </div>
        </div>
      )}

      <div className="mb-2 text-sm">
        ヒット件数：<span className="font-bold text-lg">{count}</span> 件
        {mode === 'magic' && <span className="text-slate-500 ml-2">（合成ランク = ROIC順位 + PBR順位、上位30）</span>}
      </div>

      <div className="bg-white rounded shadow overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left">
            <tr>
              <th className="px-3 py-2">コード</th>
              <th className="px-3 py-2">銘柄</th>
              {mode === 'magic' && <th className="px-3 py-2">合成ランク</th>}
              <th className="px-3 py-2">PBR</th>
              <th className="px-3 py-2">ROIC</th>
              <th className="px-3 py-2">ROE</th>
              <th className="px-3 py-2">配当利回り</th>
              <th className="px-3 py-2">Fスコア</th>
            </tr>
          </thead>
          <tbody>
            {hits.map((h) => (
              <tr key={h.code} className="border-t hover:bg-slate-50">
                <td className="px-3 py-2">
                  <Link to={`/company/${h.code}`} className="text-blue-600">{h.code}</Link>
                </td>
                <td className="px-3 py-2">{h.name}</td>
                {mode === 'magic' && <td className="px-3 py-2">{(h as any).combined_rank ?? '—'}</td>}
                <td className="px-3 py-2 font-mono">{NUM(h.pbr)}</td>
                <td className="px-3 py-2 font-mono">{PCT(h.roic)}</td>
                <td className="px-3 py-2 font-mono">{PCT(h.roe)}</td>
                <td className="px-3 py-2 font-mono">{PCT(h.dividend_yield)}</td>
                <td className="px-3 py-2 font-mono">{h.fscore ?? '—'}</td>
              </tr>
            ))}
            {hits.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-slate-400">該当なし</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-2">
      <span>{label}</span>
      {children}
    </label>
  )
}

function Check({ label, onChange }: { label: string; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2">
      <input type="checkbox" onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  )
}
