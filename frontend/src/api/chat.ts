/** 聊天 API - 流式 SSE + 工具事件解析 */
import type { Scenario } from '@/types'

export interface ChatParams {
  message: string
  scenario: Scenario
  conversation_id?: number
  user_id?: number
  stream?: boolean
  web_search_enabled?: boolean
  deep_thinking_enabled?: boolean
}

export type StreamEventType =
  | 'content' | 'rag' | 'route' | 'tools' | 'search_results' | 'reasoning' | 'thinking' | 'stopped'

export interface StreamEvent {
  type: StreamEventType
  data: any
}

// 过滤 LLM 输出中的 raw tool call / 占位文本
function sanitizeContent(text: string): string {
  if (!text) return text
  return text
    .replace(/<invoke\b[^>]*>[\s\S]*?<\/invoke>/g, '')
    .replace(/<\/?\s*tool_call\s*>/g, '')
    .replace(/<\/?invoke>/g, '')
    .replace(/\]\s*<\s*minimax\s*>\s*\[\s*<query>[\s\S]*?<\/query>\s*\]/g, '')
    .replace(/<\s*minimax\s*>/g, '')
    .replace(/<\s*\/\s*minimax\s*>/g, '')
    .replace(/[ \t]+/g, ' ')
    .trim()
}

/** 流式聊天 - AsyncGenerator, 用 yield 推 event */
export async function* streamChat(
  params: ChatParams,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent, void, unknown> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...params, stream: true, user_id: params.user_id || 1 }),
    signal,
  })
  if (!response.body) throw new Error('No response body')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    // v0.8.0: 客户端 abort 时立即退出循环, 不要等网络
    if (signal?.aborted) {
      console.log('[streamChat] aborted by user')
      return
    }
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value)
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') return
        try {
          const parsed = JSON.parse(data)
          if (!parsed.content) continue
          // 解析 [TAG]...[/TAG] 事件
          if (parsed.content.includes('[RAG]') && parsed.content.includes('[/RAG]')) {
            const m = parsed.content.match(/\[RAG\](.*?)\[\/RAG\]/)
            if (m) { yield { type: 'rag', data: JSON.parse(m[1]) }; continue }
          }
          if (parsed.content.includes('[ROUTE]') && parsed.content.includes('[/ROUTE]')) {
            const m = parsed.content.match(/\[ROUTE\](.*?)\[\/ROUTE\]/)
            if (m) { yield { type: 'route', data: JSON.parse(m[1]) }; continue }
          }
          if (parsed.content.includes('[TOOL_CALLS]')) {
            const m = parsed.content.match(/\[TOOL_CALLS\](.*?)\[\/TOOL_CALLS\]/)
            if (m) { yield { type: 'tools', data: JSON.parse(m[1]) }; continue }
          }
          if (parsed.content.includes('[TOOL_RESULTS]')) {
            const m = parsed.content.match(/\[TOOL_RESULTS\](.*?)\[\/TOOL_RESULTS\]/)
            if (m) { yield { type: 'search_results', data: JSON.parse(m[1]) }; continue }
          }
          if (parsed.content.includes('[THINKING]') && parsed.content.includes('[/THINKING]')) {
            const m = parsed.content.match(/\[THINKING\](.*?)\[\/THINKING\]/)
            if (m) { yield { type: 'thinking', data: m[1] }; continue }
          }
          if (parsed.content.includes('[REASONING]') && parsed.content.includes('[/REASONING]')) {
            const m = parsed.content.match(/\[REASONING\](.*?)\[\/REASONING\]/)
            if (m) { yield { type: 'reasoning', data: JSON.parse(m[1]) }; continue }
          }
          if (parsed.content.includes('[STOPPED]')) {
            yield { type: 'stopped', data: parsed.content }
            continue
          }
          yield { type: 'content', data: sanitizeContent(parsed.content) }
        } catch {}
      }
    }
  }
}
