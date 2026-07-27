import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts'
import { api, MatrixPoint, MatrixResponse } from '../api'

const QUADRANT_COLOR: Record<string, string> = {
  honmei: '#16a34a',
  value_trap: '#dc2626',
  healthy_expensive: '#2563eb',
  out: '#9ca3af',
}
const QUADRANT_LABEL: Record<string, string> = {
  honmei: '本命ゾーン（低PBR×高Fスコア）',
  value_trap: 'バリュートラップ警告（低PBR×低Fスコア）',
  healthy_expensive: '健全だが割高（高PBR×高Fスコア）',
  out: '対象外（高PBR×低Fスコア）',
}

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const p: MatrixPoint = payload[0].payload
  return (
    <div className="bg-white border rounded shadow px-3 py-2 text-xs">
      <div className="font-bold">{p.name}（{p.code}）</div>
      <div>PBR: {p.pbr?.toFixed(2) ?? '—'}</div>
      <div>Fスコア: {p.fscore ?? '—'}</div>
      <div>ROE: {p.roe != null ? (p.roe * 100).toFixed(1) + '%' : '—'}</div>
      {p.high_roe_low_pbr && <div className="text-green-700">★ 高ROE×低PBR</div>}
      <div className="text-slate-400 mt-1">クリックで詳細</div>
    </div>
  )
}

export default function MatrixPage() {
  const [data, setData] = useState<MatrixResponse | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()

  const load = () => api.matrix().then(setData).catch((e) => setError(String(e)))
  useEffect(() => { load() }, [])

  const seed = async () => {
    setBusy(true)
    try {
      for (const code of ['7203', '6758', '9984', '8306', '4502']) {
        await api.ingest(code, 'mock')
      }
      await load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const points = (data?.points ?? []).filter((p) => p.pbr != null && p.fscore != null)

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-bold">銘柄マトリクス</h1>
        <span className="text-sm text-slate-500">横軸 PBR（左が割安）× 縦軸 Fスコア（上が健全）</span>
        <button
          onClick={seed}
          disabled={busy}
          className="ml-auto text-sm bg-slate-800 text-white px-3 py-1.5 rounded disabled:opacity-50"
        >
          {busy ? '取込中…' : 'サンプル取込（mock）'}
        </button>
      </div>

      {error && <div className="text-red-600 text-sm mb-3">{error}</div>}

      {points.length === 0 ? (
        <div className="border border-dashed rounded p-10 text-center text-slate-500">
          データがありません。「サンプル取込（mock）」で銘柄を投入するか、
          スクリーニングや予想Excel取込から始めてください。
        </div>
      ) : (
        <div className="bg-white rounded shadow p-4">
          <ResponsiveContainer width="100%" height={460}>
            <ScatterChart margin={{ top: 20, right: 30, bottom: 40, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number" dataKey="pbr" name="PBR"
                label={{ value: 'PBR（左が割安）', position: 'bottom' }}
              />
              <YAxis
                type="number" dataKey="fscore" name="Fスコア" domain={[0, 9]}
                ticks={[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]}
                label={{ value: 'Fスコア（上が健全）', angle: -90, position: 'insideLeft' }}
              />
              <ZAxis range={[80, 260]} />
              <ReferenceLine x={data?.pbr_threshold ?? 1} stroke="#94a3b8" strokeDasharray="4 4" />
              <ReferenceLine y={data?.fscore_healthy ?? 7} stroke="#94a3b8" strokeDasharray="4 4" />
              <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: '3 3' }} />
              <Scatter
                data={points}
                onClick={(pt: any) => pt?.code && nav(`/company/${pt.code}`)}
                cursor="pointer"
              >
                {points.map((p, i) => (
                  <Cell
                    key={i}
                    fill={QUADRANT_COLOR[p.quadrant ?? 'out']}
                    stroke={p.high_roe_low_pbr ? '#000' : undefined}
                    strokeWidth={p.high_roe_low_pbr ? 2 : 0}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-4 text-xs">
            {Object.entries(QUADRANT_LABEL).map(([k, label]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full inline-block" style={{ background: QUADRANT_COLOR[k] }} />
                {label}
              </div>
            ))}
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full inline-block border-2 border-black" />
              ★ 高ROE×低PBR（追加ハイライト）
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
