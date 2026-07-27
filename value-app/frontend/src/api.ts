// バックエンド（FastAPI）への型付きクライアント。計算はすべてサーバ側。
// フロントは表示に徹する（仕様書 2章）。

const BASE = '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ---- 型 ----

export interface Company {
  code: string
  name: string
  sector?: string | null
  market_cap?: number | null
  growth_type?: string | null
  moat_tags?: string | null
  qualitative_note?: string | null
  is_cyclical: boolean
}

export interface MatrixPoint {
  code: string
  name: string
  pbr: number | null
  fscore: number | null
  roe: number | null
  quadrant: 'honmei' | 'value_trap' | 'healthy_expensive' | 'out' | null
  high_roe_low_pbr: boolean
}

export interface MatrixResponse {
  pbr_threshold: number
  fscore_healthy: number
  points: MatrixPoint[]
}

export interface FScoreItem {
  number: number
  name: string
  category: string
  passed: boolean
  detail: string
  score: number
}

export interface FScoreResult {
  total: number
  mode: string
  is_healthy: boolean
  is_unhealthy: boolean
  items: FScoreItem[]
}

export interface Metrics {
  fiscal_period: string
  [key: string]: number | string | null
}

export interface MetricsResponse {
  code: string
  metrics: Metrics[]
  changes: Record<string, { improved: boolean | null; delta: number | null }> | null
}

export interface ThresholdCriteria {
  dividend_yield_min?: number | null
  equity_ratio_min?: number | null
  net_cash_required?: boolean
  fcf_positive?: boolean
  roe_min?: number | null
  market_cap_max?: number | null
  price_change_3y_negative?: boolean
  fscore_min?: number | null
}

export interface ScreenHit {
  code: string
  name: string
  pbr: number | null
  roe: number | null
  roic: number | null
  fscore: number | null
  dividend_yield: number | null
  [key: string]: unknown
}

export interface Holding {
  id: number
  company_code: string
  buy_price?: number | null
  shares?: number | null
  buy_date?: string | null
  confidence?: number | null
  thesis?: string | null
}

export interface BusinessCycle {
  phase: string
  primary_indicators: string[]
  recommended_method: string
  indicator_confidence: Record<string, string>
  is_cyclical: boolean
  cyclical_note: string | null
}

// ---- エンドポイント ----

export const api = {
  disclaimer: () => req<{ disclaimer: string }>('/disclaimer'),

  companies: () => req<Company[]>('/companies'),
  company: (code: string) => req<Company>(`/companies/${code}`),
  createCompany: (body: unknown) =>
    req<Company>('/companies', { method: 'POST', body: JSON.stringify(body) }),

  metrics: (code: string) => req<MetricsResponse>(`/companies/${code}/metrics`),
  fscore: (code: string) => req<FScoreResult>(`/companies/${code}/fscore`),

  matrix: () => req<MatrixResponse>('/matrix'),

  screenThreshold: (criteria: ThresholdCriteria) =>
    req<{ count: number; hits: ScreenHit[] }>('/screen/threshold', {
      method: 'POST',
      body: JSON.stringify(criteria),
    }),
  screenMagic: (topN = 30) =>
    req<{ count: number; results: ScreenHit[] }>(`/screen/magic?top_n=${topN}`, {
      method: 'POST',
    }),

  holdings: () => req<Holding[]>('/holdings'),
  addHolding: (body: unknown) =>
    req<Holding>('/holdings', { method: 'POST', body: JSON.stringify(body) }),
  deleteHolding: (id: number) =>
    req<{ deleted: boolean }>(`/holdings/${id}`, { method: 'DELETE' }),
  diversification: () =>
    req<{ count: number; sector_counts: Record<string, number>; max_sector_share: number | null; warnings: string[] }>(
      '/portfolio/diversification',
    ),

  ingest: (code: string, provider = 'mock') =>
    req<{ code: string; statements_added: number }>(
      `/companies/${code}/ingest?provider=${provider}`,
      { method: 'POST' },
    ),

  businessCyclePhases: () => req<{ phases: string[] }>('/business-cycle/phases'),
  businessCycle: (phase: string, isCyclical = false) =>
    req<BusinessCycle>('/business-cycle', {
      method: 'POST',
      body: JSON.stringify({ phase, is_cyclical: isCyclical }),
    }),

  valuation: (body: unknown) =>
    req<Record<string, unknown>>('/valuation', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // 予想Excel
  excelPreview: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(BASE + '/excel/preview', { method: 'POST', body: fd }).then((r) => {
      if (!r.ok) throw new Error(String(r.status))
      return r.json() as Promise<ExcelPreviewResponse>
    })
  },
  excelExtract: (code: string, body: ExcelExtractBody) =>
    req<{ values: Record<string, number | string | null>; saved: boolean }>(
      `/companies/${code}/excel/extract`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  forecastFscore: (code: string, overrides: Record<string, number>) =>
    req<FScoreResult>(`/companies/${code}/fscore/forecast`, {
      method: 'POST',
      body: JSON.stringify(overrides),
    }),
}

export interface ExcelSuggestion {
  field: string
  sheet: string
  label_cell: string
  value_cell: string | null
  value: unknown
}

export interface ExcelPreviewResponse {
  file_id: string
  sheets: string[]
  preview: Record<string, { cell: string; value: unknown }[][]>
  suggestions: Record<string, ExcelSuggestion>
  saved_profiles: unknown[]
}

export interface ExcelExtractBody {
  file_id: string
  mapping: Record<string, { sheet: string; cell: string }>
  fiscal_period?: string | null
  scenario?: string
  source?: string
  save?: boolean
  save_profile_as?: string | null
}
