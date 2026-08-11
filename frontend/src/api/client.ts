/** API 客户端 - axios 实例 + 通用 fetch 封装 */
import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 120000 })

export default api
