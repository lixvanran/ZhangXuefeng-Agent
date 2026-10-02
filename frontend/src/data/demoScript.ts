/**
 * 首页空状态下的示例问题 + 演示用户档案
 *
 * ⚠️ v0.10.0 说明 —— 这个文件是**重建**的, 不是原作者的版本。
 *
 * 背景: `ChatPage.tsx:10` 一直在 `import { demoScripts, demoProfile } from
 * '@/data/demoScript'`, 但 `src/data/` 目录在仓库的**全部 18 个提交里都不存在**
 * (已用 `git rev-list --all | xargs git ls-tree` 逐个 commit 验证)。
 * 后果是前端**根本构建不了**:
 *
 *     $ vite build
 *     error during build:
 *     [vite:load-fallback] Could not load .../src/data/demoScript: ENOENT
 *
 * 之所以一直没被发现: `启动.bat` 走的是 `npm run dev`(vite dev server),
 * dev 模式不做类型检查也不做产物构建, 把问题掩盖了;
 * 而 `npm run build` = `tsc && vite build`, 会在第一步就失败。
 *
 * 因此本文件按**当前调用点的实际类型要求**补齐(见下), 内容为合理占位。
 * 如果你手里有原来的版本, 直接覆盖本文件即可, 只要满足以下契约:
 *
 *   - demoScripts: Record<Scenario, string[]>
 *       Scenario = 'volunteer' | 'exam' | 'chat'
 *       ChatPage 只取前 3 个渲染成快捷按钮, 超过 25 字会截断
 *   - demoProfile: UserProfile
 *       字段见 @/types 的 UserProfile 接口
 *
 * 另外注意 `ChatPage.tsx:154` 的用法是
 * `getUserProfile().catch(() => demoProfile as any)`,
 * 即**仅在接口调用失败时**才回退到这份演示档案 ——
 * 正常情况下用户档案来自后端, 所以这里的值只影响"后端挂了"的兜底体验。
 */
import type { Scenario, UserProfile } from '@/types'

/** 每个场景下, 空状态展示的示例问题(前端取前 3 个) */
export const demoScripts: Record<Scenario, string[]> = {
  volunteer: [
    '我考了 620 分, 湖南文科, 有什么推荐的院校和专业?',
    '计算机和电气工程哪个更适合就业?',
    '想学医, 但听说要读八年, 值不值?',
    '帮我分析一下冲稳保应该怎么排?',
    '这个分数能上哪些 211?',
  ],
  exam: [
    '距离高考还有 100 天, 数学应该怎么复习?',
    '英语听力总也听不清, 有没有针对性方法?',
    '理综时间不够用, 怎么分配?',
    '每次模考成绩不稳定, 怎么调整心态?',
    '错题本该怎么整理才有用?',
  ],
  chat: [
    '我很焦虑, 觉得考不上怎么办?',
    '你觉得学计算机以后会找不到工作吗?',
    '普通家庭的孩子, 努力还有用吗?',
    '我现在该选文科还是理科?',
    '能不能给我讲讲你是怎么想问题的?',
  ],
}

/**
 * 演示用户档案 —— 仅在 getUserProfile() 接口失败时兜底使用。
 * 取一个中性的"高三考生"设定, 避免给出过于具体(可能不实)的分数与位次。
 */
export const demoProfile: UserProfile = {
  id: 0,
  name: '同学',
  education_stage: 'high',
  province: null,
  score: null,
  rank: null,
  target: null,
  interests: null,
  background: null,
}
