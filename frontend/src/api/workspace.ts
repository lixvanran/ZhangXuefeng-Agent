/** Workspace API - v0.9.1 新增 */
import api from './client'

export async function uploadToWorkspace(file: File, onProgress?: (pct: number) => void): Promise<{
  success: boolean
  filename?: string
  original_name?: string
  path?: string
  size?: number
  message?: string
  error?: string
}> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    formData.append('file', file)
    formData.append('user_id', '1')

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    })
    xhr.addEventListener('load', () => {
      try {
        const data = JSON.parse(xhr.responseText)
        resolve(data)
      } catch (e) {
        reject(e)
      }
    })
    xhr.addEventListener('error', () => reject(new Error('网络错误')))
    xhr.addEventListener('abort', () => reject(new Error('上传取消')))

    xhr.open('POST', '/api/workspace/upload')
    xhr.send(formData)
  })
}

export async function listUploads(): Promise<{
  success: boolean
  items: Array<{ name: string; path: string; size: number; mtime: number }>
  total: number
}> {
  return api.get('/workspace/uploads')
}
