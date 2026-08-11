/** 客户端 feature toggle - localStorage 持久化 */
const TOGGLE_KEYS = {
  web_search: 'zxf_web_search_enabled',
  deep_thinking: 'zxf_deep_thinking_enabled',
} as const

export function getToggle(key: 'web_search' | 'deep_thinking'): boolean {
  const v = localStorage.getItem(TOGGLE_KEYS[key])
  if (v === null) return key === 'web_search' // 默认 web_search 开, deep_thinking 关
  return v === '1'
}

export function setToggle(key: 'web_search' | 'deep_thinking', value: boolean) {
  localStorage.setItem(TOGGLE_KEYS[key], value ? '1' : '0')
}
