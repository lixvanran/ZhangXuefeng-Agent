/** 资料 API - 错题 / 学习资料 */
import api from './client'
import type { Resource } from '@/types'

export const listResources = (params?: {
  type?: 'mistake' | 'material'
  subject?: string
  search?: string
  user_id?: number
}) =>
  api.get<{ total: number; items: Resource[] }>('/resources/list', { params }).then(r => r.data)

export const createResource = (formData: FormData) =>
  api.post('/resources/create', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)

export const updateResource = (id: number, formData: FormData) =>
  api.post(`/resources/${id}/update`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)

export const markResourceMastered = (id: number) =>
  api.post(`/resources/${id}/master`).then(r => r.data)

export const deleteResource = (id: number) =>
  api.delete(`/resources/${id}`).then(r => r.data)

export const getResourceStats = (user_id = 1) =>
  api.get('/resources/stats', { params: { user_id } }).then(r => r.data)

export const getResource = (id: number) =>
  api.get<Resource>(`/resources/${id}`).then(r => r.data)

export const searchResources = (query: string, top_k = 5, type?: string) =>
  api.post('/resources/search', null, { params: { query, top_k, type } }).then(r => r.data)
