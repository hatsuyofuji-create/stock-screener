import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, Company, ExcelPreviewResponse, FScoreResult } from '../api'

const FIELD_LABEL: Record<string, string> = {
  eps: '予想EPS', bps: '予想BPS', dps: '予想DPS', revenue: '売上高',
  operating_income: '営業利益', operating_margin: '営業利益率',
  net_income: '純利益', roe: 'ROE', qualitative_note: '定性メモ（前提）',
}
const FIELDS = Object.keys(FIELD_LABEL)
// 予想Fスコアの上書きに使う数値フィールド（RawFinancials の項目）
const FSCORE_OVERRIDE_FIELDS = ['revenue', 'operating_income', 'net_income']

interface CellMap { sheet: string; cell: string }

export default function ExcelPage() {
  const [preview, setPreview] = useState<ExcelPreviewResponse | null>(null)
  const [fileName, setFileName] = useState('')
  const [mapping, setMapping] = useState<Record<string, CellMap>>({})
  const [companies, setCompanies] = useState<Company[]>([])
  const [code, setCode] = useState('')
  const [fiscalPeriod, setFiscalPeriod] = useState('')
  const [scenario, setScenario] = useState('base')
  const [profileName, setProfileName] = useState('')
  const [values, setValues] = useState<Record<string, number | string | null> | null>(null)
  const [actual, setActual] = useState<FScoreResult | null>(null)
  const [forecast, setForecast] = useState<FScoreResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.companies().then(setCompanies).catch(() => {}) }, [])

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true); setError(''); setFileName(file.name)
    setValues(null); setForecast(null); setActual(null)
    try {
      const res = await api.excelPreview(file)
      setPreview(res)
      // 自動検出結果でマッピングを初期化
      const init: Record<string, CellMap> = {}
      for (const [field, s] of Object.entries(res.suggestions)) {
        if (s.value_cell) init[field] = { sheet: s.sheet, cell: s.value_cell }
      }
      setMapping(init)
    } catch (err) {
      setError('Excel を読み込めませんでした: ' + String(err))
    } finally {
      setBusy(false)
    }
  }

  const setCell = (field: string, patch: Partial<CellMap>) =>
    setMapping((m) => ({ ...m, [field]: { sheet: m[field]?.sheet ?? preview?.sheets[0] ?? '', cell: m[field]?.cell ?? '', ...patch } }))

  const extract = async () => {
    if (!preview || !code) return
    setBusy(true); setError('')
    try {
      const activeMapping: Record<string, CellMap> = {}
      for (const [f, m] of Object.entries(mapping)) {
        if (m.cell?.trim()) activeMapping[f] = { sheet: m.sheet, cell: m.cell.trim() }
      }
      const res = await api.excelExtract(code, {
        file_id: preview.file_id,
        mapping: activeMapping,
        fiscal_period: fiscalPeriod || null,
        scenario,
        save: !!fiscalPeriod,
        save_profile_as: profileName || null,
      })
      setValues(res.values)

      // 予想Fスコア：抽出した数値を最新実績に上書きして算出
      const overrides: Record<string, number> = {}
      for (const f of FSCORE_OVERRIDE_FIELDS) {
        const v = res.values[f]
        if (typeof v === 'number') overrides[f] = v
      }
      try {
        setForecast(await api.forecastFscore(code, overrides))
      } catch (e) {
        setForecast(null); setError('予想Fスコア算出には最低2期分の実績が必要です。' + String(e))
      }
      // 実績Fスコア（比較用。2期未満なら 400 → 無視）
      api.fscore(code).then(setActual).catch(() => setActual(null))
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-2">予想Excel 取込 → 予想Fスコア</h1>
      <p className="text-sm text-slate-500 mb-4">
        様式は固定しません。見出し（EPS・売上高・営業利益・前提 等）を自動検出し、確認・修正のうえ
        銘柄に紐づけて保存、最新実績に予想値を差し替えて<b>予想版Fスコア</b>を算出します（仕様書 4.6／4.2）。
      </p>

      {/* STEP1: アップロード */}
      <div className="bg-white rounded shadow p-4 mb-4">
        <div className="text-sm font-bold mb-2">① Excel をアップロード</div>
        <input type="file" accept=".xlsx" onChange={onFile} />
        {busy && <span className="ml-3 text-sm text-slate-500">解析中…</span>}
        {fileName && !busy && <span className="ml-3 text-sm text-slate-500">{fileName}</span>}
        {preview && <div className="text-xs text-slate-400 mt-1">シート：{preview.sheets.join(' / ')}</div>}
      </div>

      {error && <div className="text-red-600 text-sm mb-3 whitespace-pre-wrap">{error}</div>}

      {/* STEP2: マッピング確認・修正 */}
      {preview && (
        <div className="bg-white rounded shadow p-4 mb-4">
          <div className="text-sm font-bold mb-2">② マッピングを確認・修正</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 text-left">
                <tr>
                  <th className="px-3 py-2">項目</th>
                  <th className="px-3 py-2">シート</th>
                  <th className="px-3 py-2">セル</th>
                  <th className="px-3 py-2">検出値</th>
                </tr>
              </thead>
              <tbody>
                {FIELDS.map((field) => {
                  const s = preview.suggestions[field]
                  const m = mapping[field]
                  return (
                    <tr key={field} className="border-t">
                      <td className="px-3 py-2 font-medium">{FIELD_LABEL[field]}</td>
                      <td className="px-3 py-2">
                        <select className="border rounded px-1 py-0.5" value={m?.sheet ?? preview.sheets[0]}
                          onChange={(e) => setCell(field, { sheet: e.target.value })}>
                          {preview.sheets.map((sh) => <option key={sh} value={sh}>{sh}</option>)}
                        </select>
                      </td>
                      <td className="px-3 py-2">
                        <input className="border rounded px-2 py-0.5 w-24 font-mono"
                          placeholder="例 B3" value={m?.cell ?? ''}
                          onChange={(e) => setCell(field, { cell: e.target.value })} />
                      </td>
                      <td className="px-3 py-2 font-mono text-slate-500">{s ? String(s.value ?? '—') : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* STEP3: 銘柄に紐づけて抽出・保存 */}
      {preview && (
        <div className="bg-white rounded shadow p-4 mb-4">
          <div className="text-sm font-bold mb-2">③ 銘柄に紐づけて抽出・保存</div>
          <div className="grid md:grid-cols-4 gap-3 text-sm items-end">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">対象銘柄</span>
              <select className="border rounded px-2 py-1" value={code} onChange={(e) => setCode(e.target.value)}>
                <option value="">選択…</option>
                {companies.map((c) => <option key={c.code} value={c.code}>{c.code} {c.name}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">予想決算期（例 2026-03）</span>
              <input className="border rounded px-2 py-1" placeholder="2026-03"
                value={fiscalPeriod} onChange={(e) => setFiscalPeriod(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">シナリオ</span>
              <select className="border rounded px-2 py-1" value={scenario} onChange={(e) => setScenario(e.target.value)}>
                <option value="base">base</option>
                <option value="negative">negative</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">マッピング保存名（任意）</span>
              <input className="border rounded px-2 py-1" placeholder="park24_annual"
                value={profileName} onChange={(e) => setProfileName(e.target.value)} />
            </label>
          </div>
          {companies.length === 0 && (
            <p className="text-xs text-amber-700 mt-2">
              銘柄が未登録です。先に「銘柄マトリクス」でサンプル取込するか、銘柄を登録してください。
            </p>
          )}
          <button onClick={extract} disabled={busy || !code}
            className="mt-3 bg-slate-800 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50">
            {busy ? '処理中…' : '抽出して予想Fスコアを算出'}
          </button>
          {fiscalPeriod === '' && <span className="ml-2 text-xs text-slate-400">※決算期を入れると Forecast に保存されます</span>}
        </div>
      )}

      {/* STEP4: 結果 */}
      {values && (
        <div className="bg-white rounded shadow p-4">
          <div className="text-sm font-bold mb-2">④ 抽出結果と予想Fスコア</div>
          <div className="grid md:grid-cols-3 gap-2 text-sm mb-4">
            {Object.entries(values).map(([f, v]) => (
              <div key={f} className="border rounded p-2">
                <div className="text-xs text-slate-500">{FIELD_LABEL[f] ?? f}</div>
                <div className="font-mono">{v === null ? '—' : String(v)}</div>
              </div>
            ))}
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <FScoreCard title="予想版Fスコア" result={forecast} accent />
            <FScoreCard title="実績版Fスコア（比較）" result={actual} />
          </div>
          {code && (
            <Link to={`/company/${code}`} className="inline-block mt-3 text-sm text-blue-600">
              → {code} の銘柄詳細へ
            </Link>
          )}
        </div>
      )}
    </div>
  )
}

function FScoreCard({ title, result, accent }: { title: string; result: FScoreResult | null; accent?: boolean }) {
  return (
    <div className={`rounded p-3 border ${accent ? 'border-slate-800' : 'border-slate-200'}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="font-bold">{title}</span>
        {result && (
          <span className={`text-2xl ${result.is_healthy ? 'text-green-600' : result.is_unhealthy ? 'text-red-600' : 'text-slate-700'}`}>
            {result.total}/9
          </span>
        )}
      </div>
      {!result ? (
        <p className="text-xs text-slate-400">（2期以上の実績が必要）</p>
      ) : (
        <ul className="text-xs divide-y">
          {result.items.map((it) => (
            <li key={it.number} className="py-0.5 flex items-center gap-2">
              <span className={it.passed ? 'text-green-600' : 'text-slate-300'}>{it.passed ? '●' : '○'}</span>
              <span>{it.number}. {it.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
