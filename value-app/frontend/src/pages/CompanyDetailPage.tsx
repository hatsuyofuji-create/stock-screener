import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { api, Company, FScoreResult, MetricsResponse } from '../api'

const PCT = (v: unknown) => (typeof v === 'number' ? (v * 100).toFixed(1) + '%' : '—')
const NUM = (v: unknown) => (typeof v === 'number' ? v.toFixed(2) : '—')

export default function CompanyDetailPage() {
  const { code } = useParams<{ code: string }>()
  const [company, setCompany] = useState<Company | null>(null)
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [fscore, setFscore] = useState<FScoreResult | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!code) return
    api.company(code).then(setCompany).catch((e) => setError(String(e)))
    api.metrics(code).then(setMetrics).catch(() => {})
    api.fscore(code).then(setFscore).catch(() => setFscore(null))
  }, [code])

  const trend = (metrics?.metrics ?? []).map((m) => ({
    period: m.fiscal_period as string,
    ROA: typeof m.roa === 'number' ? m.roa * 100 : null,
    ROIC: typeof m.roic === 'number' ? m.roic * 100 : null,
    営業利益率: typeof m.operating_margin === 'number' ? m.operating_margin * 100 : null,
  }))
  const latest = metrics?.metrics?.[metrics.metrics.length - 1]

  return (
    <div>
      <Link to="/" className="text-sm text-blue-600">← マトリクスへ戻る</Link>
      {error && <div className="text-red-600 text-sm">{error}</div>}
      {company && (
        <div className="flex items-baseline gap-3 mt-2 mb-4">
          <h1 className="text-xl font-bold">{company.name}</h1>
          <span className="text-slate-500">{company.code}</span>
          {company.sector && <span className="text-xs bg-slate-200 rounded px-2 py-0.5">{company.sector}</span>}
          {company.growth_type && <span className="text-xs bg-slate-200 rounded px-2 py-0.5">{company.growth_type}</span>}
          {company.is_cyclical && <span className="text-xs bg-orange-200 rounded px-2 py-0.5">シクリカル</span>}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* Fスコア内訳 */}
        <section className="bg-white rounded shadow p-4">
          <h2 className="font-bold mb-2">
            Fスコア（実績版）
            {fscore && (
              <span className={`ml-2 text-2xl ${fscore.is_healthy ? 'text-green-600' : fscore.is_unhealthy ? 'text-red-600' : 'text-slate-700'}`}>
                {fscore.total}/9
              </span>
            )}
          </h2>
          {!fscore ? (
            <p className="text-sm text-slate-500">Fスコアには2期以上の財務データが必要です。</p>
          ) : (
            <ul className="text-sm divide-y">
              {fscore.items.map((it) => (
                <li key={it.number} className="py-1 flex items-start gap-2">
                  <span className={it.passed ? 'text-green-600' : 'text-slate-300'}>
                    {it.passed ? '●' : '○'}
                  </span>
                  <div>
                    <div>{it.number}. {it.name}</div>
                    <div className="text-xs text-slate-400">{it.detail}</div>
                  </div>
                  <span className="ml-auto text-xs text-slate-400">{it.category}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* 財務トレンド */}
        <section className="bg-white rounded shadow p-4">
          <h2 className="font-bold mb-2">収益性トレンド（%）</h2>
          {trend.length === 0 ? (
            <p className="text-sm text-slate-500">財務データがありません。</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trend}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="ROA" stroke="#16a34a" />
                <Line type="monotone" dataKey="ROIC" stroke="#2563eb" />
                <Line type="monotone" dataKey="営業利益率" stroke="#f59e0b" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </section>

        {/* 主要指標（最新期） */}
        <section className="bg-white rounded shadow p-4">
          <h2 className="font-bold mb-2">主要指標（最新期）</h2>
          {latest ? (
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Metric label="ROA（経常/総資産）" value={PCT(latest.roa)} />
              <Metric label="ROIC" value={PCT(latest.roic)} />
              <Metric label="ROE" value={PCT(latest.roe)} />
              <Metric label="自己資本比率" value={PCT(latest.equity_ratio)} />
              <Metric label="営業利益率" value={PCT(latest.operating_margin)} />
              <Metric label="流動比率" value={NUM(latest.current_ratio)} />
              <Metric label="純有利子負債" value={NUM(latest.net_interest_bearing_debt)} />
              <Metric label="CCC（日）" value={NUM(latest.ccc)} />
            </div>
          ) : (
            <p className="text-sm text-slate-500">—</p>
          )}
          <p className="text-xs text-slate-400 mt-2">
            収益性の主指標は ROA / ROIC（ROE はレバレッジで水増しされるため）。
          </p>
        </section>

        {/* 定性メモ */}
        <section className="bg-white rounded shadow p-4">
          <h2 className="font-bold mb-2">定性メモ（前提）</h2>
          <p className="text-sm whitespace-pre-wrap text-slate-700">
            {company?.qualitative_note || '（未登録。予想Excelの「前提」欄取込などで反映されます）'}
          </p>
          {company?.moat_tags && (
            <div className="mt-2 flex gap-1 flex-wrap">
              {company.moat_tags.split(',').map((t) => (
                <span key={t} className="text-xs bg-emerald-100 text-emerald-800 rounded px-2 py-0.5">{t}</span>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border rounded p-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="font-mono">{value}</div>
    </div>
  )
}
