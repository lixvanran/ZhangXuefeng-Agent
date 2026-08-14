import { create } from 'zustand'
import type { Scenario, Message, UserProfile, EducationStage, Conversation } from '@/types'

interface AppState {
  // Scenario
  scenario: Scenario
  setScenario: (s: Scenario) => void

  // Current conversation
  conversationId: number | null
  setConversationId: (id: number | null) => void

  // Messages
  messages: Message[]
  addMessage: (msg: Message) => void
  updateLastMessage: (content: string) => void
  clearMessages: () => void
  loadMessages: (msgs: Message[]) => void

  // User profile
  userProfile: UserProfile | null
  setUserProfile: (profile: UserProfile) => void

  // Streaming state
  isStreaming: boolean
  setStreaming: (b: boolean) => void

  // Conversation history
  conversations: Conversation[]
  setConversations: (convs: Conversation[]) => void
  removeConversation: (id: number) => void
}

export const useAppStore = create<AppState>((set) => ({
  scenario: 'volunteer',
  // v0.9.1: 修 bug — 切换场景不再清空当前对话, 用户需要主动点"新对话"才会建新对话
  setScenario: (s) => set({ scenario: s }),

  conversationId: null,
  setConversationId: (id) => set({ conversationId: id }),

  messages: [],
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  updateLastMessage: (content) =>
    set((state) => {
      const newMessages = [...state.messages]
      if (newMessages.length > 0) {
        newMessages[newMessages.length - 1] = {
          ...newMessages[newMessages.length - 1],
          content,
        }
      }
      return { messages: newMessages }
    }),
  clearMessages: () => set({ messages: [], conversationId: null }),
  loadMessages: (msgs) => set({ messages: msgs }),

  userProfile: null,
  setUserProfile: (profile) => set({ userProfile: profile }),

  isStreaming: false,
  setStreaming: (b) => set({ isStreaming: b }),

  conversations: [],
  setConversations: (convs) => set({ conversations: convs }),
  removeConversation: (id) =>
    set((state) => ({
      conversations: state.conversations.filter(c => c.id !== id),
    })),
}))
