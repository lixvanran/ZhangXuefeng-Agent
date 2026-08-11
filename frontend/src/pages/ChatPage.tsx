import { useState, useRef, useEffect } from 'react'
import { Send, GraduationCap, MessageCircle, Target, Loader2, Plus, MessageSquare, Trash2, Volume2, Square } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeHighlight from 'rehype-highlight'
import { useAppStore } from '@/store/useAppStore'
import { streamChat, getUserProfile, listConversations, getConversation, createConversation, deleteConversation, getToggle, setToggle, tts, getVoices } from '@/api'
import { demoScripts, demoProfile } from '@/data/demoScript'
import type { Scenario } from '@/types'

const scenarioConfig: Record<Scenario, { label: string; icon: any; color: string; gradient: string }> = {
  volunteer: { label: '志愿填报', icon: Target, color: 'text-emerald-700', gradient: 'from-emerald-500/10 to-teal-500/10' },
  exam: { label: '考前备考', icon: GraduationCap, color: 'text-blue-700', gradient: 'from-blue-500/10 to-indigo-500/10' },
  chat: { label: '随便聊聊', icon: MessageCircle, color: 'text-violet-700', gradient: 'from-violet-500/10 to-fuchsia-500/10' },
}

export default function ChatPage() {
  const {
    scenario, setScenario,
    messages, addMessage, updateLastMessage, clearMessages, loadMessages,
    conversationId, setConversationId,
    isStreaming, setStreaming,
    conversations, setConversations, removeConversation,
  } = useAppStore()

  const [input, setInput] = useState('')
  const [webSearchOn, setWebSearchOn] = useState(() => getToggle('web_search'))
  const [deepThinkingOn, setDeepThinkingOn] = useState(() => getToggle('deep_thinking'))
  const abortRef = useRef<AbortController | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const toggleWebSearch = () => {
    const next = !webSearchOn
    setWebSearchOn(next)
    setToggle('web_search', next)
  }
  const toggleDeepThinking = () => {
    const next = !deepThinkingOn
    setDeepThinkingOn(next)
    setToggle('deep_thinking', next)
  }

  // ===== TTS (v0.7.9.4) =====
  const [playingMsgIdx, setPlayingMsgIdx] = useState<number | null>(null)
  const [ttsLoading, setTtsLoading] = useState<number | null>(null)
  const [ttsError, setTtsError] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [activeVoiceId, setActiveVoiceId] = useState<string>('male-qn-qingse')
  useEffect(() => {
    // Load active voice id on mount
    getVoices().then(v => setActiveVoiceId(v.active_voice_id)).catch(() => {})
  }, [])
  const handleSpeak = async (text: string, msgIdx: number) => {
    if (playingMsgIdx === msgIdx && audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      setPlayingMsgIdx(null)
      return
    }
    setTtsError(null)
    setTtsLoading(msgIdx)
    try {
      // Clean text: strip markdown
      const clean = text
        .replace(/```[\s\S]*?```/g, '')
        .replace(/`[^`]+`/g, '')
        .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
        .replace(/#+\s/g, '')
        .replace(/\*\*([^\*]+)\*\*/g, '$1')
        .replace(/!\[([^\]]*)\]\([^\)]+\)/g, '')
        .replace(/\|[^\n]+\|/g, '')
        .replace(/<\|[^|]+\|>/g, '')
        .trim()
      if (!clean) { setTtsLoading(null); return }
      const blob = await tts(clean, undefined, 1.05)
      const url = URL.createObjectURL(blob)
      if (audioRef.current) {
        audioRef.current.pause()
      }
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => { setPlayingMsgIdx(null); URL.revokeObjectURL(url) }
      audio.onerror = () => { setPlayingMsgIdx(null); setTtsError(msgIdx); URL.revokeObjectURL(url) }
      audio.play()
      setPlayingMsgIdx(msgIdx)
    } catch (e: any) {
      console.error('TTS failed', e)
      // 503 = TTS 未配置, 弹个明确提示
      const status = e?.response?.status
      if (status === 503) {
        const detail = e?.response?.data?.detail
        const msg = detail?.message || 'TTS 未配置'
        alert(`${msg}\n\n如需朗读功能，请到 https://platform.MiniMax.io 申请 key 并填到 .env 的 MINIMAX_API_KEY。`)
      }
      setTtsError(msgIdx)
    } finally {
      setTtsLoading(null)
    }
  }

  useEffect(() => {
    loadUserAndConversations()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadUserAndConversations = async () => {
    try {
      const [profile, convs] = await Promise.all([
        getUserProfile().catch(() => demoProfile as any),
        listConversations(50),
      ])
      useAppStore.getState().setUserProfile(profile)
      setConversations(convs.items)
    } catch (e) {
      console.error(e)
    }
  }

  const handleSend = async (text?: string) => {
    const messageText = (text || input).trim()
    if (!messageText || isStreaming) return

    addMessage({ role: 'user', content: messageText })
    setInput('')
    setStreaming(true)
    addMessage({ role: 'assistant', content: '' })

    // New AbortController for this request — can be cancelled by Stop button
    const ac = new AbortController()
    abortRef.current = ac

    try {
      let fullContent = ''
      let stopped = false
      for await (const event of streamChat({
        message: messageText,
        scenario,
        conversation_id: conversationId || undefined,
        web_search_enabled: webSearchOn,
        deep_thinking_enabled: deepThinkingOn,
      }, ac.signal)) {
        if (event.type === 'content') {
          fullContent += event.data
          updateLastMessage(fullContent)
        } else if (event.type === 'rag') {
          // Attach RAG info to last assistant message
          useAppStore.setState((state) => {
            const newMsgs = [...state.messages]
            if (newMsgs.length > 0) {
              newMsgs[newMsgs.length - 1] = {
                ...newMsgs[newMsgs.length - 1],
                rag_used: event.data,
              }
            }
            return { messages: newMsgs }
          })
        } else if (event.type === 'route') {
          // 显示当前用的模型 + 复杂度档位
          useAppStore.setState((state) => {
            const newMsgs = [...state.messages]
            if (newMsgs.length > 0) {
              const r = event.data as any
              newMsgs[newMsgs.length - 1] = {
                ...newMsgs[newMsgs.length - 1],
                route: {
                  complexity: r.complexity,
                  model: r.model,
                  tier_description: r.tier_description,
                  reason: r.reason,
                },
              }
            }
            return { messages: newMsgs }
          })
        } else if (event.type === 'thinking') {
          // 深度思考流式增量
          useAppStore.setState((state) => {
            const newMsgs = [...state.messages]
            if (newMsgs.length > 0) {
              const last = newMsgs[newMsgs.length - 1]
              newMsgs[newMsgs.length - 1] = {
                ...last,
                reasoning: (last.reasoning || '') + (event.data as string),
              }
            }
            return { messages: newMsgs }
          })
        } else if (event.type === 'tools') {
          console.log('Tools used:', (event.data as any[]).map(t => t.name).join(', '))
        } else if (event.type === 'search_results') {
          // Append to message's search_results list
          useAppStore.setState((state) => {
            const newMsgs = [...state.messages]
            if (newMsgs.length > 0) {
              const last = newMsgs[newMsgs.length - 1]
              const existing = last.search_results || []
              newMsgs[newMsgs.length - 1] = {
                ...last,
                search_results: [...existing, event.data],
              }
            }
            return { messages: newMsgs }
          })
        } else if (event.type === 'reasoning') {
          // Replace content with clean answer + attach reasoning
          const ans = (event.data as any).answer || fullContent
          const thinking = (event.data as any).thinking || ''
          useAppStore.setState((state) => {
            const newMsgs = [...state.messages]
            if (newMsgs.length > 0) {
              newMsgs[newMsgs.length - 1] = {
                ...newMsgs[newMsgs.length - 1],
                content: ans,
                reasoning: thinking,
              }
            }
            return { messages: newMsgs }
          })
        } else if (event.type === 'stopped') {
          // Server confirmed user abort
          stopped = true
          useAppStore.setState((state) => {
            const newMsgs = [...state.messages]
            if (newMsgs.length > 0) {
              const last = newMsgs[newMsgs.length - 1]
              newMsgs[newMsgs.length - 1] = {
                ...last,
                content: last.content + '\n\n_(⏹ 已叫停)_',
              }
            }
            return { messages: newMsgs }
          })
        }
      }
      const convs = await listConversations(50)
      setConversations(convs.items)
      if (!conversationId && convs.items.length > 0) {
        setConversationId(convs.items[0].id)
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        // Expected on user stop
        useAppStore.setState((state) => {
          const newMsgs = [...state.messages]
          if (newMsgs.length > 0) {
            const last = newMsgs[newMsgs.length - 1]
            if (!last.content.includes('已叫停')) {
              newMsgs[newMsgs.length - 1] = {
                ...last,
                content: last.content + '\n\n_(⏹ 已叫停)_',
              }
            }
          }
          return { messages: newMsgs }
        })
      } else {
        updateLastMessage(`Error: ${error.message}`)
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  const handleStop = () => {
    if (abortRef.current) {
      abortRef.current.abort()
      // v0.8.0: 立即给视觉反馈, 不要等 SSE 关 + 后端 LLM 停 (可能 1-2s)
      useAppStore.setState((state) => {
        const newMsgs = [...state.messages]
        if (newMsgs.length > 0) {
          const last = newMsgs[newMsgs.length - 1]
          if (last.role === 'assistant' && !last.content.includes('叫停中')) {
            newMsgs[newMsgs.length - 1] = {
              ...last,
              content: last.content + '\n\n_(⏹ 叫停中...)_',
            }
          }
        }
        return { messages: newMsgs }
      })
    }
  }

  const handleNewChat = async () => {
    try {
      const newConv = await createConversation(scenario)
      setConversationId(newConv.id)
      clearMessages()
      const convs = await listConversations(50)
      setConversations(convs.items)
    } catch (e) {
      console.error(e)
      clearMessages()
    }
  }

  const handleLoadConversation = async (id: number) => {
    try {
      const conv = await getConversation(id)
      setConversationId(id)
      loadMessages(conv.messages || [])
    } catch (e) {
      console.error(e)
    }
  }

  const handleDeleteConversation = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this conversation?')) return
    try {
      await deleteConversation(id)
      removeConversation(id)
      if (conversationId === id) {
        clearMessages()
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleDemoClick = (script: string) => handleSend(script)

  const ScenarioIcon = scenarioConfig[scenario].icon

  return (
    <div className="flex h-full">
      {/* Left sidebar: scenarios + history (苹果风) */}
      <div className="w-72 apple-glass-strong flex flex-col border-r border-black/5">
        <div className="p-4 border-b border-black/5">
          <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">选择场景</h3>
          <div className="space-y-1.5">
            {(Object.keys(scenarioConfig) as Scenario[]).map((s) => {
              const config = scenarioConfig[s]
              const Icon = config.icon
              const isActive = scenario === s
              return (
                <button
                  key={s}
                  onClick={() => { setScenario(s); handleNewChat() }}
                  className={`w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-black text-white shadow-sm'
                      : 'text-zinc-700 hover:bg-black/5'
                  }`}
                >
                  <Icon size={16} className={isActive ? '' : config.color} />
                  <span>{config.label}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* New chat button */}
        <div className="p-4 border-b border-black/5">
          <button
            onClick={handleNewChat}
            className="apple-btn apple-btn-primary w-full"
          >
            <Plus size={14} />
            新对话
          </button>
        </div>

        {/* History */}
        <div className="flex-1 overflow-y-auto p-4">
          <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">历史对话</h3>
          {conversations.length === 0 ? (
            <div className="text-xs text-zinc-400 text-center py-4">还没有对话</div>
          ) : (
            <div className="space-y-1">
              {conversations.slice(0, 30).map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => handleLoadConversation(conv.id)}
                  className={`group flex items-center gap-2 p-2.5 rounded-lg cursor-pointer text-xs transition-colors ${
                    conversationId === conv.id ? 'bg-black/5' : 'hover:bg-black/[0.03]'
                  }`}
                >
                  <MessageSquare size={12} className="text-zinc-400 flex-shrink-0" />
                  <span className="flex-1 truncate text-zinc-700">{conv.title}</span>
                  <button
                    onClick={(e) => handleDeleteConversation(conv.id, e)}
                    className="opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-red-500"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col relative">
        {/* Demo scripts banner (苹果风 hero) */}
        <div className={`relative overflow-hidden border-b border-black/5 bg-gradient-to-r ${scenarioConfig[scenario].gradient}`}>
          <div className="px-6 py-4">
            <div className="flex items-center gap-2 mb-3">
              <ScenarioIcon size={16} className={scenarioConfig[scenario].color} />
              <span className="text-sm font-semibold text-zinc-800">
                {scenarioConfig[scenario].label}
              </span>
              <span className="ml-auto text-xs text-zinc-400">小峰老师</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {demoScripts[scenario].slice(0, 3).map((script, i) => (
                <button
                  key={i}
                  onClick={() => handleDemoClick(script)}
                  disabled={isStreaming}
                  className="text-xs px-3 py-1.5 bg-white/70 hover:bg-white border border-white/60 rounded-full text-zinc-700 hover:text-zinc-900 hover:shadow-sm transition-all disabled:opacity-50 backdrop-blur"
                >
                  {script.length > 25 ? script.slice(0, 25) + '...' : script}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Feature toggles */}
        <div className="px-6 py-2 border-b border-black/5 bg-white/40 backdrop-blur flex items-center gap-4 text-sm">
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <div className="relative">
              <input
                type="checkbox"
                checked={webSearchOn}
                onChange={toggleWebSearch}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-zinc-300 rounded-full peer-checked:bg-blue-500 transition-colors" />
              <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full peer-checked:translate-x-4 transition-transform" />
            </div>
            <span className={webSearchOn ? 'text-blue-700 font-medium' : 'text-zinc-500'}>
              联网搜索
            </span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <div className="relative">
              <input
                type="checkbox"
                checked={deepThinkingOn}
                onChange={toggleDeepThinking}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-zinc-300 rounded-full peer-checked:bg-purple-500 transition-colors" />
              <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full peer-checked:translate-x-4 transition-transform" />
            </div>
            <span className={deepThinkingOn ? 'text-purple-700 font-medium' : 'text-zinc-500'}>
              深度思考
            </span>
          </label>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center px-6 apple-fade-in">
              <h1 className="apple-h1 mb-3">
                问点什么？
              </h1>
              <p className="apple-sub max-w-md mb-8">
                分数、位次、想去的城市、想学的专业 —<br />
                小峰老师用 15 年经验 + 真实录取数据给你方案。
              </p>
              <div className="flex items-center gap-2 text-xs text-zinc-400">
                <span>点击上方</span>
                <span className="px-2 py-0.5 bg-white/60 rounded-full border border-white/40">剧本按钮</span>
                <span>快速体验</span>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-5">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} apple-fade-in`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                      msg.role === 'user'
                        ? 'bg-black text-white rounded-tr-md shadow-sm'
                        : 'bg-white/80 backdrop-blur border border-black/5 shadow-sm rounded-tl-md'
                    }`}
                  >
                      {msg.role === 'assistant' && (
                        <div className="flex items-center gap-2 mb-2 pb-2 border-b border-black/5">
                          <span className="text-xs font-semibold text-zinc-800">小峰老师</span>
                        </div>
                      )}
                    {msg.role === 'user' ? (
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    ) : msg.content ? (
                      <div>
                        {/* 路由信息 (复杂度 + 选用模型) */}
                        {msg.route && (
                          <div className="mb-2 flex items-center gap-2 text-xs text-gray-500">
                            <span className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                              {msg.route.complexity}
                            </span>
                            <span className="font-mono text-gray-600">{msg.route.model}</span>
                            {msg.route.reason && <span className="text-gray-400">· {msg.route.reason}</span>}
                          </div>
                        )}
                        {/* 思考过程小窗 (deep thinking) */}
                        {msg.reasoning && (
                          <details className="mb-3 bg-purple-50 border border-purple-200 rounded-lg">
                            <summary className="px-3 py-2 cursor-pointer text-sm font-medium text-purple-700 flex items-center gap-2">
                              <span>深度思考过程</span>
                              <span className="text-xs text-purple-500 ml-auto">点击展开</span>
                            </summary>
                            <div className="px-3 py-2 text-sm text-gray-700 whitespace-pre-wrap border-t border-purple-200">
                              {msg.reasoning}
                            </div>
                          </details>
                        )}
                        {/* 搜索过程小窗 (web search) */}
                        {msg.search_results && msg.search_results.length > 0 && (
                          <details className="mb-3 bg-blue-50 border border-blue-200 rounded-lg" open>
                            <summary className="px-3 py-2 cursor-pointer text-sm font-medium text-blue-700 flex items-center gap-2">
                              <span>联网搜索过程 · {msg.search_results.length} 个工具调用</span>
                            </summary>
                            <div className="px-3 py-2 text-sm space-y-2 border-t border-blue-200">
                              {msg.search_results.map((sr, idx) => {
                                const r = sr.result || {}
                                const results = r.results || []
                                const provider = r.provider || 'none'
                                const query = (sr.args as any)?.query || (sr.args as any)?.province || ''
                                return (
                                  <div key={idx} className="bg-white rounded p-2 border border-blue-100">
                                    <div className="flex items-center gap-2 text-xs text-gray-600 mb-1">
                                      <span className="font-mono bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded">{sr.tool}</span>
                                      <span className="text-gray-500">来源: {provider}</span>
                                      {r.success ? (
                                        <span className="text-green-600">搜到 {results.length} 条</span>
                                      ) : (
                                        <span className="text-orange-600">搜索未返回结果</span>
                                      )}
                                    </div>
                                    {query && <div className="text-xs text-gray-700 mb-1">关键词: {query}</div>}
                                    {results.length > 0 && (
                                      <div className="space-y-1.5 mt-1.5">
                                        {results.slice(0, 3).map((item: any, i: number) => (
                                          <div key={i} className="text-xs">
                                            <a
                                              href={item.url}
                                              target="_blank"
                                              rel="noopener noreferrer"
                                              className="text-blue-700 hover:underline font-medium block"
                                            >
                                              [{i + 1}] {item.title}
                                            </a>
                                            {item.content && (
                                              <div className="text-gray-500 line-clamp-2 mt-0.5">{item.content}</div>
                                            )}
                                          </div>
                                        ))}
                                        {results.length > 3 && (
                                          <div className="text-xs text-gray-400">还有 {results.length - 3} 条...</div>
                                        )}
                                      </div>
                                    )}
                                    {r.error && (
                                      <div className="text-xs text-orange-600 mt-1">原因: {r.error}</div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          </details>
                        )}
                        <div className="markdown-body text-gray-800">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm, remarkMath]}
                            rehypePlugins={[rehypeKatex, rehypeHighlight]}
                          >
                            {msg.content}
                          </ReactMarkdown>
                          {isStreaming && i === messages.length - 1 && <span className="cursor-blink"></span>}
                        </div>
                        {msg.rag_used && ((msg.rag_used.user_resources?.length ?? 0) > 0 || (msg.rag_used.kb_results?.length ?? 0) > 0) && (
                          <div className="mt-2 pt-2 border-t border-gray-100 flex flex-wrap gap-1">
                            {msg.rag_used.user_resources?.map((r) => (
                              <span key={r.code} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded">
                                <span className="font-mono">{r.code}</span>
                                <span className="truncate max-w-[120px]">{r.title}</span>
                                {r.has_file && <span className="text-xs">文件</span>}
                              </span>
                            ))}
                            {msg.rag_used.kb_results?.slice(0, 2).map((r, i) => (
                              <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-50 text-purple-700 text-xs rounded">
                                KB: {r.title}
                              </span>
                            ))}
                          </div>
                        )}
                        {/* 朗读 按钮 (v0.7.9.4) */}
                        <div className="mt-2 pt-2 border-t border-gray-100 flex items-center gap-2">
                          <button
                            onClick={() => handleSpeak(msg.content, i)}
                            disabled={ttsLoading === i}
                            className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md transition ${
                              playingMsgIdx === i
                                ? 'bg-orange-100 text-orange-700 hover:bg-orange-200'
                                : ttsError === i
                                ? 'bg-red-50 text-red-600 hover:bg-red-100'
                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                            }`}
                            title={playingMsgIdx === i ? '点击停止' : '用 AI 模仿张老师的声音朗读'}
                          >
                            {ttsLoading === i ? (
                              <><Loader2 size={12} className="animate-spin" /> 合成中...</>
                            ) : playingMsgIdx === i ? (
                              <><Square size={12} fill="currentColor" /> 停止</>
                            ) : ttsError === i ? (
                              <><Volume2 size={12} /> 重试</>
                            ) : (
                              <><Volume2 size={12} /> 朗读</>
                            )}
                          </button>
                          <span className="text-xs text-gray-400">
                            {ttsError === i ? '朗读失败' : playingMsgIdx === i ? '播放中' : '张老师的声音'}
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-gray-400">
                        <Loader2 size={14} className="animate-spin" />
                        <span className="text-sm">思考中...</span>
                      </div>
                    )}
                    </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input (苹果风) */}
        <div className="p-4 border-t border-black/5 bg-white/60 backdrop-blur-xl">
          <div className="max-w-3xl mx-auto flex gap-2 items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder={`问小峰老师关于${scenarioConfig[scenario].label}的问题...`}
              className="apple-input resize-none"
              rows={2}
              disabled={isStreaming}
            />
            <button
              onClick={isStreaming ? handleStop : () => handleSend()}
              disabled={!isStreaming && !input.trim()}
              className={`apple-btn ${
                isStreaming
                  ? 'bg-orange-500 text-white hover:bg-orange-600'
                  : 'apple-btn-primary disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:scale-100'
              }`}
              title={isStreaming ? '叫停张老师' : '发送'}
            >
              {isStreaming ? (
                <>
                  <span className="w-2.5 h-2.5 bg-white rounded-sm" />
                  <span>叫停中</span>
                </>
              ) : (
                <>
                  <Send size={16} />
                  <span>发送</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
