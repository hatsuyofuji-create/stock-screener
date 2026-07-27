import { useState } from 'react'
import { api } from '../api'

interface Suggestion {
  field: string
  sheet: string
  label_cell: string
  value_cell: string | null
  value: unknown
}

const FIELD_LABEL: Record<string, string> = {
  eps: '予想EPS', bps: '予想BPS', dps: '予想DPS', revenue: '売上高',
  operating_income: '営業利益', operating_margin: '営業利益率',
  net_income: '純利益', roe: 'ROE', qualitative_note: '定性メモ（前提）',
}

export default function ExcelPage() {
  const [sheets, setSheets] = useState<string[]>([])
  const [suggestions, setSuggestions] = useState<Record<string, Suggestion>>({})
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true); setError(''); setFileName(file.name)
    try {
      const res = await api.excelPreview(file)
      setSheets(res.sheets ?? [])
      setSuggestions(res.suggestions ?? {})
    } catch (err) {
      setError('Excel を読み込めませんでした: ' + String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">予想Excel 取込</h1>
      <p className="text-sm text-slate-500 mb-4">
        様式は固定しません。アップロードすると見出し（EPS・BPS・DPS・売上高・営業利益・前提 等）を
        自動検出し、値セルの候補を提案します（仕様書 4.6）。
      </p>

      <div className="bg-white rounded shadow p-4 mb-4">
        <input type="file" accept=".xlsx" onChange={onFile} />
        {busy && <span className="ml-3 text-sm text-slate-500">解析中…</span>}
        {fileName && !busy && <span className="ml-3 text-sm text-slate-500">{fileName}</span>}
      </div>

      {error && <div className="text-red-600 text-sm mb-3">{error}</div>}

      {sheets.length > 0 && (
        <div className="text-sm text-slate-500 mb-2">シート：{sheets.join(' / ')}</div>
      )}

      {Object.keys(suggestions).length > 0 && (
        <div className="bg-white rounded shadow overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-left">
              <tr>
                <th className="px-3 py-2">項目</th>
                <th className="px-3 py-2">検出シート</th>
                <th className="px-3 py-2">見出しセル</th>
                <th className="px-3 py-2">値セル</th>
                <th className="px-3 py-2">検出値</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(suggestions).map(([field, s]) => (
                <tr key={field} className="border-t">
                  <td className="px-3 py-2 font-medium">{FIELD_LABEL[field] ?? field}</td>
                  <td className="px-3 py-2">{s.sheet}</td>
                  <td className="px-3 py-2 font-mono">{s.label_cell}</td>
                  <td className="px-3 py-2 font-mono">{s.value_cell ?? '—'}</td>
                  <td className="px-3 py-2 font-mono">{String(s.value ?? '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-slate-400 p-3">
            この自動検出結果を確認・修正のうえ、銘柄に紐づけて保存します
            （抽出→Forecast保存 API：<code>/api/companies/&#123;code&#125;/excel/extract</code>）。
          </p>
        </div>
      )}
    </div>
  )
}
