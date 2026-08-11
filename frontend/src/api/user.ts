/** 用户 API */
import api from './client'
import type { UserProfile, EducationStageOption } from '@/types'

export const getUserProfile = () =>
  api.get<UserProfile>('/user/profile').then(r => r.data)

export const updateUserProfile = (data: Partial<UserProfile>) =>
  api.put('/user/profile', null, { params: data }).then(r => r.data)

export const getEducationStages = () =>
  api.get<{ stages: EducationStageOption[] }>('/user/education-stages').then(r => r.data.stages)
