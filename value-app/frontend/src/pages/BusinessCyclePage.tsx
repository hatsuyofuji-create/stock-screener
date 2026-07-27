import { useEffect, useState } from 'react'
import { api, BusinessCycle } from '../api'

const METHOD_LABEL: Record<string, string> = {
  per: 'PER基準（適正株価 = 予想EPS × 妥当PER）',
  pbr: 'PBR基準（適正株価 = 予想BPS × 妥当PBR）',
  dividend: '配当利回り基準（適正株価 = 予想DPS ÷ 妥当利回り）',
}

export default function BusinessCyclePage() {
  const [phases, setPhases] = useState<string[]>([])
  const [phase, setPhase] = useState('')
  const [cyclical, setCyclical] = useState(false)
  const [result, setResult] = useState<BusinessCycle | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.businessCyclePhases().then((r) => {
      setPhases(r.phases)
      setPhase(r.phases[0] ?? '')
    }).catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!phase) return
    api.businessCycle(phase, cyclical).then(setResult).catch((e) => setError(String(e)))
  }, [phase, cyclical])

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">景気局面セレクター</h1>
      <p className="text-sm text-slate-500 mb-4">
        現在の景気局面に応じて、適正株価計算の主指標を自動で切り替えます（仕様書 4.4 / 6章）。
      </p>
      {error && <div className="text-red-600 text-sm mb-3">{error}</div>}

      <div className="bg-white rounded shadow p-4 max-w-xl">
        <label className="flex items-center gap-3 mb-3">
          <span className="text-sm w-24">景気局面</span>
          <select className="border rounded px-2 py-1 flex-1" value={phase}
            onChange={(e) => setPhase(e.target.value)}>
            {phases.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 mb-4 text-sm">
          <input type="checkbox" checked={cyclical} onChange={(e) => setCyclical(e.target.checked)} />
          シクリカル銘柄として扱う（PERの高低を反転解釈）
        </label>

        {result && (
          <div className="border-t pt-3">
            <div className="text-sm text-slate-500">推奨する適正株価の基準</div>
            <div className="font-bold text-lg">{METHOD_LABEL[result.recommended_method] ?? result.recommended_method}</div>

            <div className="mt-3 text-sm text-slate-500">主指標と信頼度</div>
            <ul className="mt-1 flex flex-wrap gap-2">
              {result.primary_indicators.map((ind) => (
                <li key={ind} className="text-sm bg-slate-100 rounded px-2 py-1">
                  {ind}
                  <span className={`ml-1 text-xs ${result.indicator_confidence[ind] === '高' ? 'text-green-600' : 'text-slate-400'}`}>
                    （信頼度 {result.indicator_confidence[ind]}）
                  </span>
                </li>
              ))}
            </ul>

            {result.cyclical_note && (
              <div className="mt-3 text-sm text-orange-700 bg-orange-50 rounded p-2">
                {result.cyclical_note}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
