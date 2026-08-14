/** SettingsModal - v0.9.1 新增
- 替代原 DiagnoseModal
- 3 个 tab: API 状态 / 模型选择 / 消费
- API 状态: 原 DiagnoseModal 的功能
- 模型选择: 让用户从白名单里选 low/mid/high 档模型
- 消费: 查 OpenRouter 余额
*/
import { useState, useEffect } from 'react'
import {
  Settings, RefreshCw, CheckCircle2, XCircle, AlertTriangle,
  ExternalLink, Copy, X, Zap, ChevronDown, ChevronRight,
  Server, Activity, Wallet, Save, Loader2
} from 'lucide-react'
import api from '@/api/client'

// ===== 类型 =====

interface ModelPing {
  ok: boolean
  status_code?: number
  latency_ms?: number
  model_returned?: string
  tokens?: number
  cost?: number
  error?: string
  error_type?: 'region' | 'payment' | 'not_found' | 'network' | 'unknown'
}

interface TierConfig {
  primary: string
  fallback: string[]
}

interface DiagnoseResult {
  llm_api_key_set: boolean
  llm_api_key_prefix: string | null
  llm_base_url: string
  embedding_provider: string
  search_provider: string
  tts_enabled: boolean
  llm_test?: {
    ok: boolean
    error_code?: number
    error?: string
    diagnosis?: string
    model?: string
    message?: string
    actions?: string[]
    account?: {
      email?: string
      is_free_tier?: boolean
      limit?: number | null
      limit_remaining?: number | null
      usage?: number
      rate_limit?: any
    }
  }
  tier_routing?: {
    low: TierConfig
    medium: TierConfig
    high: TierConfig
    high_trigger_rule?: string
  }
  api_call_status?: {
    pinged_at?: string
    error?: string
    models?: Record<string, ModelPing>
    summary?: { total: number; ok: number; failed: number }
  }
  high_tier_access?: {
    ok?: boolean
    model?: string
    error?: string
    impact?: string
    actions?: string[]
    error_code?: number
  }
}

interface ModelSettings {
  whitelist: Record<'low' | 'medium' | 'high', string[]>
  defaults: Record<'low' | 'medium' | 'high', string>
  current: { low: string; medium: string; high: string }
}

interface UsageInfo {
  ok: boolean
  email?: string
  is_free_tier?: boolean
  limit?: number | null
  limit_remaining?: number | null
  usage?: number | null
  error?: string
}

interface Props {
  inline?: boolean
  onClose?: () => void
}

type Tab = 'api' | 'models' | 'usage'

const TIER_LABEL: Record<'low' | 'medium' | 'high', { name: string; color: string; bg: string; border: string }> = {
  low: { name: 'LOW', color: 'text-green-700', bg: 'bg-green-50', border: 'border-green-200' },
  medium: { name: 'MEDIUM', color: 'text-blue-700', bg: 'bg-blue-50', border: 'border-blue-200' },
  high: { name: 'HIGH', color: 'text-purple-700', bg: 'bg-purple-50', border: 'border-purple-200' },
}

const TIER_DESC: Record<'low' | 'medium' | 'high', string> = {
  low: '闲聊 / 简单查询 / 1-2 步任务',
  medium: '标准问答 / 多步推理',
  high: '复杂规划 / 深度推理 (需开启 high 模式)',
}


export default function SettingsModal({ inline = false, onClose }: Props) {
  const [tab, setTab] = useState<Tab>('api')

  return (
    <div className={inline ? 'h-full overflow-hidden flex flex-col' : 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4'}>
      <div className={inline
        ? 'flex-1 overflow-hidden flex flex-col'
        : 'bg-white rounded-lg w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col'
      }>
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-black/5 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Settings size={20} className="text-orange-500" />
            <h2 className="text-xl font-bold">系统设置</h2>
          </div>
          {!inline && onClose && (
            <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded">
              <X size={20} />
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="flex border-b border-black/5 flex-shrink-0 px-5">
          <TabButton active={tab === 'api'} onClick={() => setTab('api')} icon={<Activity size={14} />}>
            API 状态
          </TabButton>
          <TabButton active={tab === 'models'} onClick={() => setTab('models')} icon={<Server size={14} />}>
            模型设置
          </TabButton>
          <TabButton active={tab === 'usage'} onClick={() => setTab('usage')} icon={<Wallet size={14} />}>
            消费/余额
          </TabButton>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {tab === 'api' && <ApiStatusTab />}
          {tab === 'models' && <ModelSettingsTab />}
          {tab === 'usage' && <UsageTab />}
        </div>
      </div>
    </div>
  )
}


function TabButton({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2.5 text-sm font-medium flex items-center gap-1.5 border-b-2 transition-colors ${
        active
          ? 'border-orange-500 text-orange-600'
          : 'border-transparent text-zinc-500 hover:text-zinc-800'
      }`}
    >
      {icon}
      {children}
    </button>
  )
}


// ===== Tab 1: API 状态 (原 DiagnoseModal 主体) =====

function ApiStatusTab() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DiagnoseResult | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const run = async () => {
    setLoading(true)
    setErr(null)
    try {
      const r = await api.get<DiagnoseResult>('/diagnose', { timeout: 60000 })
      setResult(r.data)
    } catch (e: any) {
      setErr(e?.message || '请求失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (!result) run() }, [])

  if (loading && !result) {
    return (
      <div className="flex items-center gap-2 text-gray-500 py-8 justify-center">
        <RefreshCw size={20} className="animate-spin" />
        正在检测 OpenRouter key + ping 所有 3 档模型...
        <span className="text-xs ml-2">(最多 60s)</span>
      </div>
    )
  }

  if (err) {
    return (
      <div className="space-y-3">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-2">
          <XCircle size={20} className="text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-medium text-red-800">检测请求失败</div>
            <div className="text-sm text-red-600 mt-1">{err}</div>
          </div>
        </div>
        <button onClick={run} className="px-3 py-1.5 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600 flex items-center gap-1">
          <RefreshCw size={14} /> 重试
        </button>
      </div>
    )
  }

  if (!result) return null

  return (
    <div className="space-y-4">
      {/* 总状态 */}
      <div className={`rounded-lg p-4 flex items-start gap-3 ${
        result.llm_test?.ok ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
      }`}>
        {result.llm_test?.ok ? (
          <CheckCircle2 size={24} className="text-green-500 flex-shrink-0" />
        ) : (
          <XCircle size={24} className="text-red-500 flex-shrink-0" />
        )}
        <div className="flex-1">
          <div className="font-semibold">
            {result.llm_test?.ok ? '✓ OpenRouter key 有效' : '✗ key 验证失败'}
          </div>
          {result.llm_test?.message && (
            <div className="text-sm text-zinc-600 mt-1">{result.llm_test.message}</div>
          )}
          {result.llm_test?.error && (
            <div className="text-sm text-red-600 mt-1">{result.llm_test.error}</div>
          )}
          {result.llm_test?.account && (
            <div className="text-sm text-zinc-600 mt-1">
              {result.llm_test.account.email && <span>账号: {result.llm_test.account.email} · </span>}
              {result.llm_test.account.is_free_tier !== undefined && (
                <span>{result.llm_test.account.is_free_tier ? '免费版' : '付费版'}</span>
              )}
            </div>
          )}
        </div>
        <button onClick={run} disabled={loading} className="px-3 py-1.5 text-xs bg-white border border-zinc-200 rounded-lg hover:bg-zinc-50 flex items-center gap-1">
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> 重新检测
        </button>
      </div>

      {/* 失败时的解决步骤 */}
      {!result.llm_test?.ok && result.llm_test?.actions && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
          <div className="font-medium text-amber-800 flex items-center gap-1 mb-2">
            <AlertTriangle size={16} /> 解决步骤
          </div>
          <ol className="text-sm text-amber-900 space-y-1 list-decimal list-inside">
            {result.llm_test.actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ol>
        </div>
      )}

      {/* 基础信息 */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <InfoRow label="LLM Base URL" value={result.llm_base_url} />
        <InfoRow label="Embedding" value={result.embedding_provider} />
        <InfoRow label="Search" value={result.search_provider} />
        <InfoRow label="TTS" value={result.tts_enabled ? '已启用' : '未启用'} />
        <InfoRow label="API Key" value={result.llm_api_key_prefix || '未设置'} />
      </div>

      {/* 三档配置 */}
      {result.tier_routing && (
        <div className="space-y-2">
          <div className="text-sm font-semibold text-zinc-700 flex items-center gap-1">
            <Zap size={14} /> 三档模型配置
          </div>
          {(['low', 'medium', 'high'] as const).map(tier => {
            const t = result.tier_routing![tier]
            const label = TIER_LABEL[tier]
            return (
              <div key={tier} className={`rounded-lg border p-3 ${label.border} ${label.bg}`}>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className={`text-xs font-bold ${label.color}`}>{label.name}</span>
                  <span className="text-xs text-zinc-500">{tier}</span>
                </div>
                <div className="text-sm font-mono text-zinc-800">{t.primary}</div>
                {t.fallback && t.fallback.length > 0 && (
                  <div className="text-xs text-zinc-500 mt-1">
                    fallback: {t.fallback.join(', ')}
                  </div>
                )}
              </div>
            )
          })}
          {result.tier_routing.high_trigger_rule && (
            <div className="text-xs text-zinc-500 mt-2">
              触发规则: {result.tier_routing.high_trigger_rule}
            </div>
          )}
        </div>
      )}
    </div>
  )
}


function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-zinc-50 rounded-lg px-3 py-2">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-sm font-mono text-zinc-800 mt-0.5 truncate" title={value}>{value}</div>
    </div>
  )
}


// ===== Tab 2: 模型选择 =====

function ModelSettingsTab() {
  const [settings, setSettings] = useState<ModelSettings | null>(null)
  const [selection, setSelection] = useState<{ low: string; medium: string; high: string }>({ low: '', medium: '', high: '' })
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setErr(null)
    try {
      const r = await api.get<ModelSettings>('/settings/models')
      setSettings(r.data)
      setSelection(r.data.current)
    } catch (e: any) {
      setErr(e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    setSaving(true)
    setErr(null)
    setMsg(null)
    try {
      await api.put('/settings/models', selection)
      setMsg('✓ 已保存, 下次对话生效')
      setTimeout(() => setMsg(null), 3000)
    } catch (e: any) {
      const errMsg = e?.response?.data?.detail || e?.message || '保存失败'
      setErr(errMsg)
    } finally {
      setSaving(false)
    }
  }

  if (loading && !settings) {
    return (
      <div className="flex items-center gap-2 text-gray-500 py-8 justify-center">
        <Loader2 size={20} className="animate-spin" /> 加载模型设置...
      </div>
    )
  }

  if (!settings) {
    return (
      <div className="text-red-600">加载失败: {err}</div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="text-sm text-zinc-600 bg-blue-50 border border-blue-200 rounded-lg p-3">
        💡 从每档白名单里选一个模型。<br />
        严格白名单: 只能调用下列模型, 不会乱跑别的。<br />
        默认: low=minimaxM2.7, medium/high=minimaxM3
      </div>

      {(['low', 'medium', 'high'] as const).map(tier => {
        const opts = settings.whitelist[tier] || []
        const defaultModel = settings.defaults[tier]
        const current = selection[tier]
        return (
          <div key={tier} className={`rounded-lg border p-4 ${TIER_LABEL[tier].border} ${TIER_LABEL[tier].bg}`}>
            <div className="flex items-center gap-2 mb-2">
              <span className={`text-sm font-bold ${TIER_LABEL[tier].color}`}>{TIER_LABEL[tier].name}</span>
              <span className="text-xs text-zinc-500">{TIER_DESC[tier]}</span>
            </div>
            <div className="space-y-1.5">
              {opts.map(model => (
                <label key={model} className="flex items-center gap-2 cursor-pointer hover:bg-white/60 rounded px-2 py-1.5 -mx-2">
                  <input
                    type="radio"
                    name={`tier-${tier}`}
                    value={model}
                    checked={current === model}
                    onChange={() => setSelection(prev => ({ ...prev, [tier]: model }))}
                    className="text-orange-500 focus:ring-orange-500"
                  />
                  <span className="text-sm font-mono flex-1 text-zinc-800">{model}</span>
                  {model === defaultModel && (
                    <span className="text-xs px-1.5 py-0.5 bg-white/80 text-zinc-600 rounded">默认</span>
                  )}
                </label>
              ))}
            </div>
          </div>
        )
      })}

      {err && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 flex items-start gap-2">
          <XCircle size={16} className="flex-shrink-0 mt-0.5" />
          <div>{err}</div>
        </div>
      )}

      {msg && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-700 flex items-center gap-2">
          <CheckCircle2 size={16} />
          {msg}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 flex items-center gap-1.5"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          {saving ? '保存中...' : '保存设置'}
        </button>
        <button
          onClick={load}
          disabled={loading}
          className="px-4 py-2 bg-white border border-zinc-200 rounded-lg hover:bg-zinc-50 flex items-center gap-1.5"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 重新加载
        </button>
      </div>
    </div>
  )
}


// ===== Tab 3: 消费/余额 =====

function UsageTab() {
  const [usage, setUsage] = useState<UsageInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setErr(null)
    try {
      const r = await api.get<UsageInfo>('/settings/usage')
      setUsage(r.data)
    } catch (e: any) {
      setErr(e?.message || '查询失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading && !usage) {
    return (
      <div className="flex items-center gap-2 text-gray-500 py-8 justify-center">
        <Loader2 size={20} className="animate-spin" /> 查询 OpenRouter 余额...
      </div>
    )
  }

  if (err && !usage) {
    return (
      <div className="space-y-3">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">{err}</div>
        <button onClick={load} className="px-3 py-1.5 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600 flex items-center gap-1">
          <RefreshCw size={14} /> 重试
        </button>
      </div>
    )
  }

  if (!usage) return null

  if (!usage.ok) {
    return (
      <div className="space-y-3">
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
          <div className="font-medium text-amber-800 flex items-center gap-1 mb-1">
            <AlertTriangle size={16} /> 无法查询余额
          </div>
          <div className="text-sm text-amber-700">{usage.error}</div>
        </div>
        <button onClick={load} className="px-3 py-1.5 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600 flex items-center gap-1">
          <RefreshCw size={14} /> 重试
        </button>
      </div>
    )
  }

  const limit = usage.limit
  const remaining = usage.limit_remaining
  const used = usage.usage
  const pct = limit && limit > 0 && remaining != null
    ? Math.round(((limit - remaining) / limit) * 100)
    : null

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-green-200 bg-green-50 p-5">
        <div className="text-sm text-zinc-600 mb-1">OpenRouter 账号</div>
        <div className="text-2xl font-bold text-zinc-800 mb-1">{usage.email || '(匿名)'}</div>
        <div className="text-xs text-zinc-500">
          {usage.is_free_tier ? '免费版' : '付费版'} ·
          <a href="https://openrouter.ai/keys" target="_blank" rel="noreferrer" className="ml-1 text-orange-600 hover:underline inline-flex items-center gap-0.5">
            管理 key <ExternalLink size={10} />
          </a>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Card label="总额度" value={limit != null ? `$${limit.toFixed(2)}` : '-'} />
        <Card label="已用" value={used != null ? `$${used.toFixed(2)}` : '-'} color="text-amber-600" />
        <Card label="剩余" value={remaining != null ? `$${remaining.toFixed(2)}` : '-'} color="text-green-600" />
      </div>

      {pct != null && limit != null && (
        <div className="bg-zinc-50 rounded-lg p-4">
          <div className="text-sm text-zinc-600 mb-2">使用进度</div>
          <div className="w-full bg-zinc-200 rounded-full h-3 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-amber-500' : 'bg-green-500'
              }`}
              style={{ width: `${Math.min(100, pct)}%` }}
            />
          </div>
          <div className="text-xs text-zinc-500 mt-2 text-right">{pct}%</div>
        </div>
      )}

      <div className="text-xs text-zinc-500">
        💡 数据来自 OpenRouter <code className="px-1 bg-zinc-100 rounded">/api/v1/auth/key</code>, 不消耗 token。
      </div>

      <button
        onClick={load}
        disabled={loading}
        className="px-3 py-1.5 text-sm bg-white border border-zinc-200 rounded-lg hover:bg-zinc-50 flex items-center gap-1"
      >
        <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 刷新
      </button>
    </div>
  )
}


function Card({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-zinc-50 rounded-lg p-4">
      <div className="text-xs text-zinc-500 mb-1">{label}</div>
      <div className={`text-xl font-bold ${color || 'text-zinc-800'}`}>{value}</div>
    </div>
  )
}
