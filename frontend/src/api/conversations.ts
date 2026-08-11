/** 会话 API */
import api from './client'
import type { Scenario, Conversation, ConversationWithMessages } from '@/types'

export const listConversations = (limit = 50) =>
  api.get<{ total: number; items: Conversation[] }>('/conversations/list', { params: { limit } })
    .then(r => r.data)

export const getConversation = (id: number) =>
  api.get<ConversationWithMessages>(`/conversations/${id}`).then(r => r.data)

export const createConversation = (scenario: Scenario, title?: string) =>
  api.post('/conversations/new', null, { params: { scenario, title } }).then(r => r.data)

export const updateConversationTitle = (id: number, title: string) =>
  api.patch(`/conversations/${id}`, null, { params: { title } }).then(r => r.data)

export const deleteConversation = (id: number) =>
  api.delete(`/conversations/${id}`).then(r => r.data)
