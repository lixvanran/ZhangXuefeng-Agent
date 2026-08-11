import { useState } from 'react'
import { Stethoscope, RefreshCw, CheckCircle2, XCircle, AlertTriangle, ExternalLink, Copy, X, Zap, ChevronDown, ChevronRight, Server, Activity } from 'lucide-react'
import api from '@/api/client'

// 单个模型的 ping 结果
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
  // v0.8.0: tier 路由配置
  tier_routing?: {
    low: TierConfig
    medium: TierConfig
    high: TierConfig
    high_trigger_rule?: string
  }
  // v0.8.0: API 调用情况
  api_call_status?: {
    pinged_at?: string
    error?: string
    models?: Record<string, ModelPing>
    summary?: {
      total: number
      ok: number
      failed: number
    }
  }
  // v0.8.0: 旧 high 档探测 (向后兼容)
  high_tier_access?: {
    ok?: boolean
    model?: string
    error?: string
    impact?: string
    actions?: string[]
    error_code?: number
  }
}

interface Props {
  inline?: boolean
  onClose?: () => void
}

const TIER_LABEL: Record<'low' | 'medium' | 'high', { name: string; color: string; bg: string; border: string }> = {
  low: { name: 'LOW', color: 'text-green-700', bg: 'bg-green-50', border: 'border-green-200' },
  medium: { name: 'MEDIUM', color: 'text-blue-700', bg: 'bg-blue-50', border: 'border-blue-200' },
  high: { name: 'HIGH', color: 'text-purple-700', bg: 'bg-purple-50', border: 'border-purple-200' },
}

export default function DiagnoseModal({ inline = false, onClose }: Props) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DiagnoseResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  // 折叠状态: 哪个 tier 在展开
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ low: true, medium: true, high: true })

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

  // 自动跑一次
  if (!result && !loading && !err) {
    run()
  }

  const Container = inline ? 'div' : 'div'
  const containerClass = inline
    ? 'h-full overflow-y-auto p-6'
    : 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4'

  const Card = inline ? 'div' : 'div'
  const cardClass = inline
    ? 'max-w-4xl mx-auto'
    : 'bg-white rounded-lg w-full max-w-3xl max-h-[90vh] overflow-y-auto p-6'

  return (
    <Container className={containerClass}>
      <Card className={cardClass}>
        {!inline && (
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Stethoscope size={20} className="text-orange-500" />
              <h2 className="text-xl font-bold">系统诊断</h2>
            </div>
            <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded">
              <X size={20} />
            </button>
          </div>
        )}

        {inline && (
          <div className="flex items-center gap-2 mb-4">
            <Stethoscope size={20} className="text-orange-500" />
            <h2 className="text-xl font-bold">系统诊断</h2>
            <button
              onClick={run}
              disabled={loading}
              className="ml-auto px-3 py-1.5 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 flex items-center gap-1"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              重新检测
            </button>
          </div>
        )}

        {loading && !result && (
          <div className="flex items-center gap-2 text-gray-500 py-8 justify-center">
            <RefreshCw size={20} className="animate-spin" />
            正在检测 OpenRouter key + ping 所有 3 档模型...
            <span className="text-xs ml-2">(最多 60s)</span>
          </div>
        )}

        {err && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-2">
            <XCircle size={20} className="text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-medium text-red-800">检测请求失败</div>
              <div className="text-sm text-red-600 mt-1">{err}</div>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-4">
            {/* 总体状态 */}
            <div className={`rounded-lg p-4 flex items-start gap-3 ${
              result.llm_test?.ok
                ? 'bg-green-50 border border-green-200'
                : 'bg-red-50 border border-red-200'
            }`}>
              {result.llm_test?.ok ? (
                <CheckCircle2 size={24} className="text-green-500 flex-shrink-0" />
              ) : (
                <XCircle size={24} className="text-red-500 flex-shrink-0" />
              )}
              <div className="flex-1">
                <div className={`text-lg font-bold ${
                  result.llm_test?.ok ? 'text-green-800' : 'text-red-800'
                }`}>
                  {result.llm_test?.ok ? 'OpenRouter Key 有效' : '检测出问题'}
                </div>
                <div className="text-sm mt-1 text-gray-700">
                  {result.llm_test?.ok
                    ? result.llm_test.message
                    : result.llm_test?.diagnosis || result.llm_test?.error}
                </div>
                {result.llm_test?.error_code && (
                  <div className="text-xs text-gray-500 mt-1">
                    HTTP {result.llm_test.error_code}
                  </div>
                )}
              </div>
            </div>

            {/* v0.8.0: API 调用情况 — 3 档模型实测 */}
            {result.api_call_status && !result.api_call_status.error && (
              <div className="bg-white border-2 border-gray-200 rounded-lg overflow-hidden">
                <div className="px-4 py-3 bg-gradient-to-r from-gray-50 to-gray-100 border-b border-gray-200 flex items-center gap-2">
                  <Zap size={18} className="text-yellow-500" />
                  <h3 className="font-bold text-gray-800">API 调用情况</h3>
                  {result.api_call_status.pinged_at && (
                    <span className="text-xs text-gray-500 ml-auto">
                      探测于 {result.api_call_status.pinged_at}
                    </span>
                  )}
                </div>
                {result.api_call_status.summary && (
                  <div className="px-4 py-2 flex items-center gap-4 text-sm border-b border-gray-100">
                    <span className="text-gray-600">
                      探测模型: <b>{result.api_call_status.summary.total}</b> 个
                    </span>
                    <span className="text-green-700">
                      可用: <b>{result.api_call_status.summary.ok}</b>
                    </span>
                    {result.api_call_status.summary.failed > 0 && (
                      <span className="text-red-700">
                        失败: <b>{result.api_call_status.summary.failed}</b>
                      </span>
                    )}
                  </div>
                )}

                {/* 3 档模型列表 */}
                {result.tier_routing && (
                  <div className="divide-y divide-gray-100">
                    {(['low', 'medium', 'high'] as const).map((tier) => {
                      const cfg = result.tier_routing![tier]
                      const label = TIER_LABEL[tier]
                      const isExpanded = expanded[tier]
                      const models: { model: string; role: 'primary' | 'fallback' }[] = [
                        { model: cfg.primary, role: 'primary' },
                        ...cfg.fallback.map((m) => ({ model: m, role: 'fallback' as const })),
                      ]
                      const primaryPing = result.api_call_status?.models?.[cfg.primary]
                      const primaryOk = primaryPing?.ok

                      return (
                        <div key={tier}>
                          <button
                            onClick={() => setExpanded((s) => ({ ...s, [tier]: !s[tier] }))}
                            className={`w-full px-4 py-3 flex items-center gap-3 hover:bg-gray-50 transition-colors`}
                          >
                            {isExpanded ? <ChevronDown size={16} className="text-gray-400" /> : <ChevronRight size={16} className="text-gray-400" />}
                            <span className={`px-2 py-0.5 rounded text-xs font-bold ${label.bg} ${label.color} border ${label.border}`}>
                              {label.name}
                            </span>
                            <code className="text-sm font-mono text-gray-800 flex-1 text-left truncate">
                              {cfg.primary}
                            </code>
                            {primaryOk !== undefined && (
                              primaryOk ? (
                                <span className="flex items-center gap-1 text-green-600 text-xs">
                                  <CheckCircle2 size={14} />
                                  {primaryPing?.latency_ms}ms
                                </span>
                              ) : (
                                <span className="flex items-center gap-1 text-red-600 text-xs">
                                  <XCircle size={14} />
                                  {primaryPing?.error_type || '失败'}
                                </span>
                              )
                            )}
                          </button>
                          {isExpanded && (
                            <div className="px-4 pb-3 pl-12 space-y-2">
                              {models.map(({ model, role }) => {
                                const p = result.api_call_status?.models?.[model]
                                return (
                                  <ModelRow
                                    key={model}
                                    model={model}
                                    role={role}
                                    ping={p}
                                  />
                                )
                              })}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* high 触发规则 */}
                {result.tier_routing?.high_trigger_rule && (
                  <div className="px-4 py-3 bg-purple-50 border-t border-purple-200">
                    <div className="text-xs font-semibold text-purple-800 mb-1">
                      HIGH 档触发规则 (v0.8.0):
                    </div>
                    <pre className="text-xs text-purple-900 whitespace-pre-wrap font-mono">
                      {result.tier_routing.high_trigger_rule}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* 配置详情 */}
            <div className="bg-gray-50 rounded-lg p-4 space-y-2 text-sm">
              <h3 className="font-semibold text-gray-700 mb-2">配置详情</h3>
              <Row label="LLM API Key" value={
                result.llm_api_key_set
                  ? <code className="text-xs bg-gray-200 px-1.5 py-0.5 rounded">{result.llm_api_key_prefix}</code>
                  : <span className="text-red-500">未设置</span>
              } />
              <Row label="LLM Base URL" value={<code className="text-xs">{result.llm_base_url}</code>} />
              <Row label="Embedding" value={result.embedding_provider === 'openai' ? 'OpenAI' : '本地 TF-IDF (fallback)'} />
              <Row label="Web Search" value={result.search_provider} />
              <Row label="TTS (朗读)" value={result.tts_enabled ? '已启用' : '未配置 (不影响聊天)'} />
            </div>

            {/* 修复建议 */}
            {result.llm_test && !result.llm_test.ok && result.llm_test.actions && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                <div className="flex items-center gap-2 font-semibold text-orange-800 mb-2">
                  <AlertTriangle size={16} />
                  解决步骤
                </div>
                <ol className="space-y-1.5 text-sm text-orange-900">
                  {result.llm_test.actions.map((a, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-orange-500 flex-shrink-0">{i + 1}.</span>
                      <span>{a}</span>
                    </li>
                  ))}
                </ol>
                <div className="mt-3 pt-3 border-t border-orange-200 flex flex-wrap gap-2">
                  <a
                    href="https://openrouter.ai/keys"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs px-3 py-1.5 bg-orange-500 text-white rounded hover:bg-orange-600 inline-flex items-center gap-1"
                  >
                    <ExternalLink size={12} />
                    OpenRouter Keys
                  </a>
                  <a
                    href="https://openrouter.ai/credits"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs px-3 py-1.5 bg-white border border-orange-300 text-orange-700 rounded hover:bg-orange-50 inline-flex items-center gap-1"
                  >
                    <ExternalLink size={12} />
                    余额/限额
                  </a>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(JSON.stringify(result, null, 2))
                      alert('诊断结果已复制到剪贴板')
                    }}
                    className="text-xs px-3 py-1.5 bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-50 inline-flex items-center gap-1"
                  >
                    <Copy size={12} />
                    复制结果
                  </button>
                </div>
              </div>
            )}

            {/* 成功时显示账号详情 */}
            {result.llm_test?.ok && result.llm_test.account && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-blue-800 mb-2">OpenRouter 账号信息</h3>
                <div className="space-y-1.5 text-sm text-blue-900">
                  <div>邮箱: <code className="bg-blue-100 px-1.5 py-0.5 rounded">{result.llm_test.account.email || '?'}</code></div>
                  <div>账号类型: {result.llm_test.account.is_free_tier ? '免费档' : '付费档'}</div>
                  {result.llm_test.account.limit !== null && (
                    <div>余额: <span className="font-mono">${result.llm_test.account.limit_remaining?.toFixed(2)} / ${result.llm_test.account.limit?.toFixed(2)}</span></div>
                  )}
                  {result.llm_test.account.usage !== undefined && (
                    <div>累计消费: <span className="font-mono">${result.llm_test.account.usage.toFixed(4)}</span></div>
                  )}
                </div>
              </div>
            )}

            {/* 复制按钮 (放最后, 不管成功失败都能复制) */}
            <div className="flex justify-end">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(JSON.stringify(result, null, 2))
                  alert('完整诊断结果已复制到剪贴板')
                }}
                className="text-xs px-3 py-1.5 bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-50 inline-flex items-center gap-1"
              >
                <Copy size={12} />
                复制完整 JSON
              </button>
            </div>
          </div>
        )}
      </Card>
    </Container>
  )
}

function ModelRow({ model, role, ping }: { model: string; role: 'primary' | 'fallback'; ping?: ModelPing }) {
  if (!ping) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <Server size={14} className="text-gray-400" />
        <code className="text-xs font-mono text-gray-700">{model}</code>
        <span className="text-xs text-gray-400 ml-auto">未探测</span>
      </div>
    )
  }
  if (ping.ok) {
    return (
      <div className="flex items-center gap-2 text-sm bg-green-50 -mx-2 px-2 py-1.5 rounded">
        <CheckCircle2 size={14} className="text-green-600 flex-shrink-0" />
        <code className="text-xs font-mono text-gray-800 flex-1 truncate">{model}</code>
        {role === 'primary' && <span className="text-xs bg-green-600 text-white px-1.5 py-0.5 rounded">PRIMARY</span>}
        {role === 'fallback' && <span className="text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">FB</span>}
        <span className="text-xs text-green-700 font-mono">
          {ping.latency_ms}ms
        </span>
        {ping.tokens !== undefined && (
          <span className="text-xs text-gray-500 font-mono">
            {ping.tokens}t
          </span>
        )}
        {ping.cost !== undefined && ping.cost > 0 && (
          <span className="text-xs text-orange-600 font-mono">
            ${ping.cost.toFixed(4)}
          </span>
        )}
        {ping.model_returned && ping.model_returned !== model && (
          <span className="text-xs text-gray-400" title={ping.model_returned}>
            ↪ {ping.model_returned.split('/').pop()}
          </span>
        )}
      </div>
    )
  }
  // 失败
  const errorTypeLabel: Record<string, string> = {
    region: '地区限制',
    payment: '余额不足',
    not_found: '模型不存在',
    network: '网络不通',
    unknown: '未知错误',
  }
  return (
    <div className="flex items-center gap-2 text-sm bg-red-50 -mx-2 px-2 py-1.5 rounded">
      <XCircle size={14} className="text-red-600 flex-shrink-0" />
      <code className="text-xs font-mono text-gray-800 flex-1 truncate">{model}</code>
      {role === 'primary' && <span className="text-xs bg-red-600 text-white px-1.5 py-0.5 rounded">PRIMARY</span>}
      {role === 'fallback' && <span className="text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">FB</span>}
      <span className="text-xs text-red-700 font-mono">
        {ping.status_code ? `HTTP ${ping.status_code}` : ping.error_type}
        {ping.latency_ms !== undefined && ` (${ping.latency_ms}ms)`}
      </span>
      {ping.error_type && (
        <span className="text-xs text-red-600">
          {errorTypeLabel[ping.error_type] || ping.error_type}
        </span>
      )}
      {ping.error && (
        <span className="text-xs text-gray-500 truncate max-w-xs" title={ping.error}>
          {ping.error.length > 60 ? ping.error.substring(0, 60) + '...' : ping.error}
        </span>
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-gray-500 w-32 flex-shrink-0">{label}:</span>
      <span className="text-gray-800">{value}</span>
    </div>
  )
}
