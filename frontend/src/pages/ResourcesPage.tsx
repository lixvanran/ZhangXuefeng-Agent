import { useState, useEffect, useRef } from 'react'
import { Upload, Trash2, Search, BookOpen, AlertCircle, CheckCircle, X, FileText, Edit3, Save, Sparkles, UserCircle2, Loader2 } from 'lucide-react'
import {
  listResources, createResource, deleteResource, getResource,
  updateResource, markResourceMastered, getResourceStats, streamChat
} from '@/api'
import type { Resource, ResourceType } from '@/types'

const subjects = ['数学', '语文', '英语', '物理', '化学', '生物', '历史', '地理', '政治', '计算机', '其他']
const errorTypes = [
  { value: 'calculation', label: '计算错误', color: 'bg-yellow-100 text-yellow-700' },
  { value: 'concept', label: '概念不清', color: 'bg-red-100 text-red-700' },
  { value: 'method', label: '方法不会', color: 'bg-orange-100 text-orange-700' },
  { value: 'unfamiliar', label: '题型陌生', color: 'bg-blue-100 text-blue-700' },
]

export default function ResourcesPage() {
  const [resources, setResources] = useState<Resource[]>([])
  const [stats, setStats] = useState<any>(null)
  const [activeTab, setActiveTab] = useState<ResourceType>('mistake')
  const [showUpload, setShowUpload] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [search, setSearch] = useState('')
  const [filterSubject, setFilterSubject] = useState('')

  // Detail view
  const [selected, setSelected] = useState<Resource | null>(null)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState<Partial<Resource>>({})

  // AI explain panel (in detail modal)
  const [aiMode, setAiMode] = useState<'standard' | 'zhang' | null>(null)
  const [aiStreaming, setAiStreaming] = useState(false)
  const [aiContent, setAiContent] = useState('')
  const [aiReasoning, setAiReasoning] = useState('')
  const aiAbortRef = useRef<AbortController | null>(null)

  // Upload form
  const [form, setForm] = useState({
    title: '',
    content: '',
    subject: '数学',
    knowledge_point: '',
    error_type: 'concept',
    notes: '',
    solution: '',
    thinking: '',
    tags: '',
    file: null as File | null,
  })

  useEffect(() => {
    loadData()
  }, [activeTab, search, filterSubject])

  const loadData = async () => {
    try {
      const params: any = { type: activeTab }
      if (filterSubject) params.subject = filterSubject
      if (search) params.search = search
      const [list, stat] = await Promise.all([
        listResources(params),
        getResourceStats(),
      ])
      setResources(list.items)
      setStats(stat)
    } catch (e) { console.error(e) }
  }

  const handleUpload = async () => {
    if (!form.title.trim()) {
      alert('请填写标题')
      return
    }
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('type', activeTab)
      formData.append('title', form.title)
      formData.append('content', form.content)
      formData.append('subject', form.subject)
      if (activeTab === 'mistake') {
        formData.append('knowledge_point', form.knowledge_point)
        formData.append('error_type', form.error_type)
      }
      formData.append('notes', form.notes)
      formData.append('solution', form.solution)
      formData.append('thinking', form.thinking)
      formData.append('tags', JSON.stringify(form.tags.split(',').map(t => t.trim()).filter(Boolean)))
      if (form.file) formData.append('file', form.file)

      const result = await createResource(formData)
      alert(`Created ${result.code}! 张老师现在能读到它了。`)
      setShowUpload(false)
      setForm({ title: '', content: '', subject: '数学', knowledge_point: '', error_type: 'concept', notes: '', solution: '', thinking: '', tags: '', file: null })
      await loadData()
    } catch (e: any) {
      alert('Upload failed: ' + e.message)
    } finally {
      setUploading(false)
    }
  }

  const handleAIExplain = async (mode: 'standard' | 'zhang') => {
    if (!selected) return
    if (aiStreaming) {
      aiAbortRef.current?.abort()
    }
    setAiMode(mode)
    setAiContent('')
    setAiReasoning('')
    setAiStreaming(true)
    const ac = new AbortController()
    aiAbortRef.current = ac
    try {
      const r = selected
      // 模仿表达格式：标准模式走 AI 助教（无张雪峰人设）
      // 张老师讲题模式：调用 deep_thinking，按张雪峰 persona 讲
      const userMsg = mode === 'zhang'
        ? `看 ${r.code}: ${r.title}\n\n${r.content || ''}\n\n请用张雪峰老师讲题的方式一步步给我讲明白。先问家庭条件，再分析这道题为什么错，然后给出明确判断和"下次碰到同类型的题怎么办"。结尾必须给一句金句。`
        : `错题 ${r.code}: ${r.title}\n\n题目: ${r.content || ''}\n\n请给出标准解答：1) 解题思路 2) 关键公式 3) 完整步骤 4) 答案 5) 同类题型的解法套路。`
      let full = ''
      for await (const ev of streamChat({
        message: userMsg,
        scenario: r.type === 'mistake' ? 'exam' : 'chat',
        web_search_enabled: false,
        deep_thinking_enabled: mode === 'zhang',
      }, ac.signal)) {
        if (ev.type === 'content') {
          full += ev.data
          setAiContent(full)
        } else if (ev.type === 'reasoning') {
          setAiReasoning((s) => s + ((ev.data as any).thinking || ''))
        } else if (ev.type === 'stopped') {
          break
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setAiContent((s) => s + `\n\n_（出错了：${e.message}）_`)
      }
    } finally {
      setAiStreaming(false)
      aiAbortRef.current = null
    }
  }

  const handleAIStop = () => {
    aiAbortRef.current?.abort()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this item?')) return
    await deleteResource(id)
    await loadData()
    if (selected?.id === id) setSelected(null)
  }

  const handleMaster = async (id: number) => {
    await markResourceMastered(id)
    await loadData()
  }

  const handleView = async (r: Resource) => {
    try {
      const full = await getResource(r.id!)
      setSelected(full)
      setEditForm(full)
      setEditing(false)
    } catch (e) { console.error(e) }
  }

  const handleSaveEdit = async () => {
    if (!selected) return
    try {
      const formData = new FormData()
      if (editForm.title) formData.append('title', editForm.title)
      if (editForm.content !== undefined) formData.append('content', editForm.content || '')
      if (editForm.subject !== undefined) formData.append('subject', editForm.subject || '')
      if (editForm.knowledge_point !== undefined) formData.append('knowledge_point', editForm.knowledge_point || '')
      if (editForm.error_type) formData.append('error_type', editForm.error_type)
      if (editForm.notes !== undefined) formData.append('notes', editForm.notes || '')
      if (editForm.solution !== undefined) formData.append('solution', editForm.solution || '')
      if (editForm.thinking !== undefined) formData.append('thinking', editForm.thinking || '')
      if (editForm.tags) formData.append('tags', JSON.stringify(editForm.tags))

      await updateResource(selected.id!, formData)
      const full = await getResource(selected.id!)
      setSelected(full)
      setEditForm(full)
      setEditing(false)
      await loadData()
      alert('Updated!')
    } catch (e: any) {
      alert('Update failed: ' + e.message)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">资料库</h1>
          <p className="text-sm text-gray-500 mt-1">错题 + 学习资料 · 张老师会读取它们来帮你</p>
        </div>
        <button
          onClick={() => setShowUpload(true)}
          className="px-4 py-2 bg-zxf-red text-white rounded-lg hover:bg-red-700 flex items-center gap-2"
        >
          <Upload size={18} />
          <span>添加{activeTab === 'mistake' ? '错题' : '资料'}</span>
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-4 rounded-lg shadow-sm">
            <div className="text-sm text-gray-500">总资料</div>
            <div className="text-3xl font-bold text-zxf-red mt-1">{stats.total}</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm">
            <div className="text-sm text-gray-500">错题</div>
            <div className="text-3xl font-bold text-orange-600 mt-1">{stats.by_type?.mistake || 0}</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm">
            <div className="text-sm text-gray-500">学习资料</div>
            <div className="text-3xl font-bold text-blue-600 mt-1">{stats.by_type?.material || 0}</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow-sm">
            <div className="text-sm text-gray-500">已掌握</div>
            <div className="text-3xl font-bold text-green-600 mt-1">{stats.mastered || 0}</div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg shadow-sm mb-4">
        <div className="flex border-b">
          <button
            onClick={() => setActiveTab('mistake')}
            className={`flex-1 px-4 py-3 text-sm font-medium ${
              activeTab === 'mistake'
                ? 'border-b-2 border-zxf-red text-zxf-red'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            错题本 ({stats?.by_type?.mistake || 0})
          </button>
          <button
            onClick={() => setActiveTab('material')}
            className={`flex-1 px-4 py-3 text-sm font-medium ${
              activeTab === 'material'
                ? 'border-b-2 border-blue-500 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            学习资料 ({stats?.by_type?.material || 0})
          </button>
        </div>

        <div className="p-4 flex gap-3">
          <div className="flex-1 relative">
            <Search size={16} className="absolute left-3 top-3 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索标题、内容、知识点、备注..."
              className="w-full pl-9 pr-3 py-2 border rounded-lg focus:outline-none focus:border-zxf-red"
            />
          </div>
          <select
            value={filterSubject}
            onChange={(e) => setFilterSubject(e.target.value)}
            className="px-3 py-2 border rounded-lg"
          >
            <option value="">全部学科</option>
            {subjects.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm">
        {resources.length === 0 ? (
          <div className="p-12 text-center text-gray-400">
            <div className="text-5xl mb-3">{activeTab === 'mistake' ? '错题本' : '资料'}</div>
            <p>还没有{activeTab === 'mistake' ? '错题' : '资料'}，点击右上角添加</p>
          </div>
        ) : (
          <div className="divide-y">
            {resources.map((r) => {
              const errorType = errorTypes.find(t => t.value === r.error_type)
              return (
                <div
                  key={r.id}
                  onClick={() => handleView(r)}
                  className="p-4 hover:bg-gray-50 cursor-pointer"
                >
                  <div className="flex items-start gap-4">
                    {r.file_path ? (
                      r.file_path.match(/\.(jpg|jpeg|png|gif|webp)$/i) ? (
                        <img src={r.file_path} alt="" className="w-16 h-16 object-cover rounded border" />
                      ) : (
                        <div className="w-16 h-16 rounded bg-blue-100 flex items-center justify-center">
                          <FileText size={24} className="text-blue-600" />
                        </div>
                      )
                    ) : (
                      <div className={`w-16 h-16 rounded flex items-center justify-center ${
                        activeTab === 'mistake' ? 'bg-red-100' : 'bg-blue-100'
                      }`}>
                        {activeTab === 'mistake' ?
                          <AlertCircle size={24} className="text-red-600" /> :
                          <BookOpen size={24} className="text-blue-600" />
                        }
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        {r.code && (
                          <span className="px-2 py-0.5 bg-gray-800 text-white text-xs font-mono rounded">
                            {r.code}
                          </span>
                        )}
                        {r.subject && (
                          <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">
                            {r.subject}
                          </span>
                        )}
                        {errorType && activeTab === 'mistake' && (
                          <span className={`px-2 py-0.5 text-xs rounded ${errorType.color}`}>
                            {errorType.label}
                          </span>
                        )}
                        {r.mastered && (
                          <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded flex items-center gap-1">
                            <CheckCircle size={10} />已掌握
                          </span>
                        )}
                        {r.tags?.map(t => (
                          <span key={t} className="px-2 py-0.5 bg-orange-100 text-orange-700 text-xs rounded">
                            #{t}
                          </span>
                        ))}
                      </div>
                      <div className="font-medium text-gray-800">{r.title}</div>
                      {r.knowledge_point && (
                        <div className="text-xs text-gray-500 mt-1">知识点: {r.knowledge_point}</div>
                      )}
                      {r.content && (
                        <div className="text-xs text-gray-500 mt-1 line-clamp-2">{r.content}</div>
                      )}
                      <div className="text-xs text-gray-400 mt-1">
                        {new Date(r.created_at).toLocaleString('zh-CN')}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {activeTab === 'mistake' && !r.mastered && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleMaster(r.id!) }}
                          className="px-2 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600"
                        >
                          已掌握
                        </button>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(r.id!) }}
                        className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-red-100 hover:text-red-600"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Upload modal */}
      {showUpload && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg w-full max-w-md max-h-[90vh] overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">添加{activeTab === 'mistake' ? '错题' : '学习资料'}</h3>
              <button onClick={() => setShowUpload(false)}><X size={20} /></button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-sm text-gray-600">标题 *</label>
                <input
                  type="text" value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder={activeTab === 'mistake' ? '例：圆锥曲线焦点弦问题' : '例：高三数学一轮复习笔记'}
                  className="w-full mt-1 border rounded-lg px-3 py-2"
                />
              </div>

              <div>
                <label className="text-sm text-gray-600">学科</label>
                <select
                  value={form.subject}
                  onChange={(e) => setForm({ ...form, subject: e.target.value })}
                  className="w-full mt-1 border rounded-lg px-3 py-2"
                >
                  {subjects.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

              {activeTab === 'mistake' && (
                <>
                  <div>
                    <label className="text-sm text-gray-600">知识点</label>
                    <input
                      type="text" value={form.knowledge_point}
                      onChange={(e) => setForm({ ...form, knowledge_point: e.target.value })}
                      placeholder="例：圆锥曲线 - 焦点弦"
                      className="w-full mt-1 border rounded-lg px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">错误类型</label>
                    <select
                      value={form.error_type}
                      onChange={(e) => setForm({ ...form, error_type: e.target.value })}
                      className="w-full mt-1 border rounded-lg px-3 py-2"
                    >
                      {errorTypes.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                  </div>
                </>
              )}

              <div>
                <label className="text-sm text-gray-600">题目/内容描述</label>
                <textarea value={form.content}
                  onChange={(e) => setForm({ ...form, content: e.target.value })}
                  placeholder={activeTab === 'mistake' ? '题目内容...' : '资料简介...'}
                  rows={3} className="w-full mt-1 border rounded-lg px-3 py-2" />
              </div>

              {activeTab === 'mistake' && (
                <>
                  <div>
                    <label className="text-sm text-gray-600">解法</label>
                    <textarea value={form.solution}
                      onChange={(e) => setForm({ ...form, solution: e.target.value })}
                      placeholder="这道题的正确解法..."
                      rows={2} className="w-full mt-1 border rounded-lg px-3 py-2" />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">思路</label>
                    <textarea value={form.thinking}
                      onChange={(e) => setForm({ ...form, thinking: e.target.value })}
                      placeholder="解题思路 / 思维过程..."
                      rows={2} className="w-full mt-1 border rounded-lg px-3 py-2" />
                  </div>
                </>
              )}

              <div>
                <label className="text-sm text-gray-600">备注（任何你想加的）</label>
                <textarea value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  placeholder="自己的心得、相关知识点..."
                  rows={2} className="w-full mt-1 border rounded-lg px-3 py-2" />
              </div>

              <div>
                <label className="text-sm text-gray-600">标签（逗号分隔）</label>
                <input type="text" value={form.tags}
                  onChange={(e) => setForm({ ...form, tags: e.target.value })}
                  placeholder="如：重点, 高三"
                  className="w-full mt-1 border rounded-lg px-3 py-2" />
              </div>

              <div>
                <label className="text-sm text-gray-600">附件</label>
                <label className="mt-1 flex items-center justify-center border-2 border-dashed rounded-lg p-4 cursor-pointer hover:border-zxf-red">
                  <input type="file"
                    onChange={(e) => setForm({ ...form, file: e.target.files?.[0] || null })}
                    className="hidden" />
                  {form.file ? (
                    <span className="text-sm text-gray-600">{form.file.name}</span>
                  ) : (
                    <div className="text-center text-gray-400">
                      <Upload size={20} className="mx-auto mb-1" />
                      <span className="text-xs">点击上传</span>
                    </div>
                  )}
                </label>
              </div>

              <div className="bg-yellow-50 border border-yellow-200 rounded p-2 text-xs text-yellow-700">
                保存后会生成编号（如 M-001），聊天时说"看 M-001"张老师就能找到
              </div>
            </div>

            <div className="flex gap-2 mt-6">
              <button onClick={() => setShowUpload(false)} className="flex-1 py-2 border rounded-lg hover:bg-gray-50">取消</button>
              <button onClick={handleUpload} disabled={uploading} className="flex-1 py-2 bg-zxf-red text-white rounded-lg hover:bg-red-700 disabled:opacity-50">
                {uploading ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail view modal */}
      {selected && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4 pb-3 border-b">
              <div className="flex items-center gap-2">
                {selected.code && (
                  <span className="px-2 py-1 bg-gray-800 text-white text-sm font-mono rounded">
                    {selected.code}
                  </span>
                )}
                <h3 className="text-lg font-bold">{editing ? '编辑' : ''}{selected.title}</h3>
              </div>
              <div className="flex items-center gap-2">
                {!editing && (
                  <button onClick={() => setEditing(true)} className="p-2 hover:bg-gray-100 rounded" title="编辑">
                    <Edit3 size={16} />
                  </button>
                )}
                <button onClick={() => { setSelected(null); setEditing(false) }}>
                  <X size={20} />
                </button>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex flex-wrap gap-1">
                {selected.subject && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">{selected.subject}</span>}
                {selected.knowledge_point && <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">{selected.knowledge_point}</span>}
                {selected.error_type && <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs rounded">{errorTypes.find(t => t.value === selected.error_type)?.label}</span>}
                {selected.tags?.map(t => <span key={t} className="px-2 py-0.5 bg-orange-100 text-orange-700 text-xs rounded">#{t}</span>)}
              </div>

              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-1">题目/内容</h4>
                {editing ? (
                  <textarea value={editForm.content || ''}
                    onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                    rows={4} className="w-full border rounded-lg px-3 py-2" />
                ) : (
                  <div className="text-sm text-gray-800 bg-gray-50 p-3 rounded whitespace-pre-wrap">
                    {selected.content || '(无)'}
                  </div>
                )}
              </div>

              {selected.file_path && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-1">附件</h4>
                  {selected.file_path.match(/\.(jpg|jpeg|png|gif|webp)$/i) ? (
                    <img src={selected.file_path} className="max-w-full rounded border" />
                  ) : (
                    <a href={selected.file_path} target="_blank" className="text-blue-600 text-sm underline">
                      {selected.file_path}
                    </a>
                  )}
                </div>
              )}

              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-1">解法</h4>
                {editing ? (
                  <textarea value={editForm.solution || ''}
                    onChange={(e) => setEditForm({ ...editForm, solution: e.target.value })}
                    rows={3} className="w-full border rounded-lg px-3 py-2" placeholder="正确解法..." />
                ) : (
                  <div className="text-sm text-gray-800 bg-green-50 p-3 rounded whitespace-pre-wrap">
                    {selected.solution || '(未填写)'}
                  </div>
                )}
              </div>

              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-1">思路</h4>
                {editing ? (
                  <textarea value={editForm.thinking || ''}
                    onChange={(e) => setEditForm({ ...editForm, thinking: e.target.value })}
                    rows={3} className="w-full border rounded-lg px-3 py-2" placeholder="解题思路..." />
                ) : (
                  <div className="text-sm text-gray-800 bg-yellow-50 p-3 rounded whitespace-pre-wrap">
                    {selected.thinking || '(未填写)'}
                  </div>
                )}
              </div>

              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-1">备注</h4>
                {editing ? (
                  <textarea value={editForm.notes || ''}
                    onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                    rows={3} className="w-full border rounded-lg px-3 py-2" placeholder="任何你想加的..." />
                ) : (
                  <div className="text-sm text-gray-800 bg-orange-50 p-3 rounded whitespace-pre-wrap">
                    {selected.notes || '(未填写)'}
                  </div>
                )}
              </div>

              {editing && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm text-gray-600">学科</label>
                    <select value={editForm.subject || ''}
                      onChange={(e) => setEditForm({ ...editForm, subject: e.target.value })}
                      className="w-full mt-1 border rounded-lg px-3 py-2">
                      {subjects.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  {selected.type === 'mistake' && (
                    <div>
                      <label className="text-sm text-gray-600">错误类型</label>
                      <select value={editForm.error_type || ''}
                        onChange={(e) => setEditForm({ ...editForm, error_type: e.target.value })}
                        className="w-full mt-1 border rounded-lg px-3 py-2">
                        {errorTypes.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                      </select>
                    </div>
                  )}
                </div>
              )}

              <div className="text-xs text-gray-400">
                创建于 {new Date(selected.created_at).toLocaleString('zh-CN')}
                {selected.updated_at && selected.updated_at !== selected.created_at && (
                  <> · 更新于 {new Date(selected.updated_at).toLocaleString('zh-CN')}</>
                )}
              </div>
            </div>

            <div className="flex gap-2 mt-6 pt-4 border-t">
              {editing ? (
                <>
                  <button onClick={() => { setEditing(false); setEditForm(selected) }} className="flex-1 py-2 border rounded-lg hover:bg-gray-50">取消</button>
                  <button onClick={handleSaveEdit} className="flex-1 py-2 bg-zxf-red text-white rounded-lg hover:bg-red-700 flex items-center justify-center gap-2">
                    <Save size={16} />保存
                  </button>
                </>
              ) : (
                <>
                  {selected.type === 'mistake' && !selected.mastered && (
                    <button
                      onClick={() => { handleMaster(selected.id!); setSelected({ ...selected, mastered: true }) }}
                      className="flex-1 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600"
                    >
                      标记已掌握
                    </button>
                  )}
                  <button
                    onClick={() => { handleDelete(selected.id!) }}
                    className="px-4 py-2 bg-red-100 text-red-600 rounded-lg hover:bg-red-200"
                  >
                    <Trash2 size={16} />
                  </button>
                </>
              )}
            </div>

            {/* AI 讲解面板 (只在错题时显示) */}
            {selected.type === 'mistake' && !editing && (
              <div className="mt-4 pt-4 border-t">
                <div className="flex items-center gap-2 mb-3">
                  <Sparkles size={16} className="text-purple-600" />
                  <h4 className="text-sm font-semibold text-gray-700">AI 智能讲解</h4>
                </div>
                <div className="flex gap-2 mb-3 flex-wrap">
                  <button
                    onClick={() => handleAIExplain('standard')}
                    disabled={aiStreaming && aiMode !== 'standard'}
                    className="px-3 py-1.5 bg-blue-500 text-white text-sm rounded-lg hover:bg-blue-600 disabled:opacity-50 flex items-center gap-1"
                  >
                    {aiStreaming && aiMode === 'standard' ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                    一键 AI 正解（模仿表达格式）
                  </button>
                  <button
                    onClick={() => handleAIExplain('zhang')}
                    disabled={aiStreaming && aiMode !== 'zhang'}
                    className="px-3 py-1.5 bg-zxf-red text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center gap-1"
                  >
                    {aiStreaming && aiMode === 'zhang' ? <Loader2 size={14} className="animate-spin" /> : <UserCircle2 size={14} />}
                    一键 张老师讲题
                  </button>
                  {aiStreaming && (
                    <button
                      onClick={handleAIStop}
                      className="px-3 py-1.5 bg-orange-500 text-white text-sm rounded-lg hover:bg-orange-600"
                    >
                      停止
                    </button>
                  )}
                </div>

                {aiReasoning && aiMode === 'zhang' && (
                  <details className="mb-3 bg-purple-50 border border-purple-200 rounded-lg">
                    <summary className="px-3 py-2 cursor-pointer text-sm font-medium text-purple-700">
                      张老师思考过程
                    </summary>
                    <div className="px-3 py-2 text-sm text-gray-700 whitespace-pre-wrap border-t border-purple-200">
                      {aiReasoning}
                    </div>
                  </details>
                )}

                {aiContent && (
                  <div className="bg-gradient-to-br from-gray-50 to-orange-50 border border-orange-200 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      {aiMode === 'zhang' ? (
                        <>
                          <div className="w-6 h-6 rounded-full bg-zxf-red flex items-center justify-center text-white text-xs font-bold">张</div>
                          <span className="text-sm font-semibold text-gray-700">张老师讲题</span>
                        </>
                      ) : (
                        <>
                          <Sparkles size={14} className="text-blue-600" />
                          <span className="text-sm font-semibold text-gray-700">标准解答</span>
                        </>
                      )}
                    </div>
                    <div className="markdown-body text-sm text-gray-800 whitespace-pre-wrap">
                      {aiContent}
                      {aiStreaming && <span className="inline-block w-2 h-4 bg-gray-400 ml-1 animate-pulse" />}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
