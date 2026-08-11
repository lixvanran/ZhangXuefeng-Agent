/** TTS API - 语音合成 + 声音列表 */
import api from './client'

export interface VoicePreset {
  voice_id: string
  voice_name: string
}

export interface VoicesResponse {
  active_voice_id: string
  is_cloned: boolean
  tts_enabled: boolean
  voices: VoicePreset[]
}

export const tts = async (
  text: string,
  voice_id?: string,
  speed = 1.0,
): Promise<Blob> => {
  const r = await api.post('/tts', { text, voice_id, speed }, { responseType: 'blob' })
  return r.data
}

export const getVoices = () =>
  api.get<VoicesResponse>('/tts/voices').then(r => r.data)
