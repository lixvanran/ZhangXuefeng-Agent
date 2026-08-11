import { useState, useEffect } from 'react'
import { User, Save, Sparkles } from 'lucide-react'
import { getUserProfile, updateUserProfile, getEducationStages } from '@/api'
import { useAppStore } from '@/store/useAppStore'
import type { EducationStage, EducationStageOption } from '@/types'

export default function ProfilePage() {
  const { userProfile, setUserProfile } = useAppStore()
  const [stages, setStages] = useState<EducationStageOption[]>([])
  const [form, setForm] = useState({
    name: '',
    education_stage: 'high' as EducationStage,
    province: '',
    score: '' as string | number,
    rank: '' as string | number,
    target: '',
    interests: '',
    background: '',
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadStages()
    if (userProfile) populateForm(userProfile)
  }, [userProfile])

  const loadStages = async () => {
    try {
      const data = await getEducationStages()
      setStages(data)
    } catch (e) {
      console.error(e)
    }
  }

  const populateForm = (p: any) => {
    setForm({
      name: p.name || '',
      education_stage: p.education_stage || 'high',
      province: p.province || '',
      score: p.score ?? '',
      rank: p.rank ?? '',
      target: p.target || '',
      interests: p.interests || '',
      background: p.background || '',
    })
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const data: any = {
        name: form.name || 'Student',
        education_stage: form.education_stage,
      }
      if (form.province) data.province = form.province
      if (form.score !== '') data.score = parseInt(String(form.score))
      if (form.rank !== '') data.rank = parseInt(String(form.rank))
      if (form.target) data.target = form.target
      if (form.interests) data.interests = form.interests
      if (form.background) data.background = form.background

      await updateUserProfile(data)
      const updated = await getUserProfile()
      setUserProfile(updated)
      alert('保存成功！')
    } catch (e: any) {
      alert('保存失败: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const currentStage = stages.find(s => s.value === form.education_stage)
  const showScoreRank = form.education_stage === 'high' || form.education_stage === 'vocational'

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-zxf-red to-orange-500 flex items-center justify-center text-white text-2xl font-bold">
            {form.name?.[0] || '?'}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-800">{form.name || '未设置'}</h1>
            <p className="text-sm text-gray-500 mt-1">
              {currentStage ? `${currentStage.icon} ${currentStage.label}` : '设置你的身份'}
            </p>
          </div>
        </div>

        {/* Form */}
        <div className="bg-white rounded-lg shadow-sm p-6">
          <h2 className="font-bold mb-4 flex items-center gap-2">
            <User size={18} className="text-purple-500" />
            基本信息
            <span className="text-xs text-gray-500 font-normal">（除了姓名，其他都是选填）</span>
          </h2>

          <div className="space-y-4">
            {/* Name */}
            <div>
              <label className="text-sm text-gray-600">姓名 / 昵称 *</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="怎么称呼你？"
                className="w-full mt-1 border rounded-lg px-3 py-2"
              />
            </div>

            {/* Education stage */}
            <div>
              <label className="text-sm text-gray-600">学历阶段</label>
              <div className="mt-2 grid grid-cols-5 gap-2">
                {stages.map((s) => (
                  <button
                    key={s.value}
                    onClick={() => setForm({ ...form, education_stage: s.value })}
                    className={`p-2 text-xs rounded-lg border-2 transition-all ${
                      form.education_stage === s.value
                        ? 'border-zxf-red bg-red-50 text-zxf-red'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="text-lg">{s.icon}</div>
                    <div className="mt-1">{s.label}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Province */}
            <div>
              <label className="text-sm text-gray-600">所在省份（选填）</label>
              <input
                type="text"
                value={form.province}
                onChange={(e) => setForm({ ...form, province: e.target.value })}
                placeholder="如：河南"
                className="w-full mt-1 border rounded-lg px-3 py-2"
              />
            </div>

            {/* Score & rank - only for high school */}
            {showScoreRank && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-gray-600">估分（选填）</label>
                  <input
                    type="number"
                    value={form.score}
                    onChange={(e) => setForm({ ...form, score: e.target.value })}
                    placeholder="如：580"
                    className="w-full mt-1 border rounded-lg px-3 py-2"
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-600">位次（选填）</label>
                  <input
                    type="number"
                    value={form.rank}
                    onChange={(e) => setForm({ ...form, rank: e.target.value })}
                    placeholder="如：32000"
                    className="w-full mt-1 border rounded-lg px-3 py-2"
                  />
                </div>
              </div>
            )}

            {/* Target */}
            <div>
              <label className="text-sm text-gray-600">目标 / 期望（选填）</label>
              <input
                type="text"
                value={form.target}
                onChange={(e) => setForm({ ...form, target: e.target.value })}
                placeholder="如：想读计算机相关专业 / 想考研 / 想转行..."
                className="w-full mt-1 border rounded-lg px-3 py-2"
              />
            </div>

            {/* Interests */}
            <div>
              <label className="text-sm text-gray-600">兴趣方向（选填）</label>
              <textarea
                value={form.interests}
                onChange={(e) => setForm({ ...form, interests: e.target.value })}
                placeholder="对什么方向感兴趣？比如：编程、文学、艺术..."
                rows={2}
                className="w-full mt-1 border rounded-lg px-3 py-2"
              />
            </div>

            {/* Background */}
            <div>
              <label className="text-sm text-gray-600">自我介绍（选填）</label>
              <textarea
                value={form.background}
                onChange={(e) => setForm({ ...form, background: e.target.value })}
                placeholder="简单介绍下自己，让张老师更了解你..."
                rows={3}
                className="w-full mt-1 border rounded-lg px-3 py-2"
              />
            </div>

            <button
              onClick={handleSave}
              disabled={saving}
              className="w-full py-3 bg-zxf-red text-white rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <Save size={18} />
              {saving ? '保存中...' : '保存信息'}
            </button>
          </div>
        </div>

        {/* Tip */}
        <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-700">
          <div className="flex items-center gap-2 mb-1">
            <Sparkles size={16} />
            <span className="font-semibold">小提示</span>
          </div>
          填写的信息越详细，张老师给的建议越个性化。学历阶段不同，关注点也不同：
          <ul className="mt-2 list-disc list-inside text-xs space-y-1">
            <li>小学/初中：学习方法、习惯养成</li>
            <li>高中/职高：高考志愿、专业选择</li>
            <li>本科/大专：考研、就业规划</li>
            <li>考研/留学：目标学校、专业方向</li>
            <li>在职：转行、晋升、技能提升</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
