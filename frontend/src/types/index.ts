// Type definitions

export type Scenario = 'volunteer' | 'exam' | 'chat'

export type EducationStage =
  | 'primary' | 'middle' | 'high' | 'vocational'
  | 'junior_college' | 'bachelor' | 'master' | 'abroad'
  | 'working' | 'other'

export type ResourceType = 'mistake' | 'material'

export interface Message {
  id?: number
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tool_calls?: any
  rag_used?: {
    user_resources?: Array<{ code: string; title: string; type: string; score: number; has_file?: boolean }>
    kb_results?: Array<{ title: string; type: string; score: number }>
  }
  search_results?: Array<{
    tool: string
    args: any
    result: any
  }>
  reasoning?: string
  route?: {
    complexity: 'low' | 'medium' | 'high'
    model: string
    tier_description?: string
    reason?: string
  }
  created_at?: string
}

export interface Conversation {
  id: number
  user_id: number
  scenario: Scenario
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationWithMessages extends Conversation {
  messages: Message[]
}

export interface UserProfile {
  id: number
  name: string
  education_stage: EducationStage
  province?: string | null
  score?: number | null
  rank?: number | null
  target?: string | null
  interests?: string | null
  background?: string | null
}

export interface EducationStageOption {
  value: EducationStage
  label: string
  icon: string
}

// Unified resource (replaces old WrongQuestion and Material)
export interface Resource {
  id: number
  type: ResourceType
  code?: string | null
  title: string
  content?: string | null
  file_path?: string | null
  subject?: string | null
  tags: string[]
  knowledge_point?: string | null
  error_type?: string | null
  mastered: boolean
  notes?: string | null
  solution?: string | null
  thinking?: string | null
  created_at: string
  updated_at?: string
}
