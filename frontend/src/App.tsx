import { useState } from 'react'
import { MessageSquare, FolderOpen, User, Settings } from 'lucide-react'
import ChatPage from '@/pages/ChatPage'
import ResourcesPage from '@/pages/ResourcesPage'
import ProfilePage from '@/pages/ProfilePage'
import SettingsModal from '@/components/SettingsModal'

type PageKey = 'chat' | 'resources' | 'profile'

const navItems: { key: PageKey | 'settings'; label: string; icon: any; color: string }[] = [
  { key: 'chat', label: '智能对话', icon: MessageSquare, color: 'text-red-500' },
  { key: 'resources', label: '资料库', icon: FolderOpen, color: 'text-blue-500' },
  { key: 'profile', label: '个人中心', icon: User, color: 'text-purple-500' },
  { key: 'settings', label: '系统设置', icon: Settings, color: 'text-orange-500' },
]

export default function App() {
  const [page, setPage] = useState<PageKey | 'settings'>('chat')
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <div className="flex h-screen apple-bg relative">
      {/* 苹果风毛玻璃 sidebar */}
      <aside className="w-64 apple-glass-strong flex flex-col z-10">
        <div className="p-6 border-b border-black/5">
          <div>
            <h1 className="text-lg font-bold tracking-tight">张雪峰智能体</h1>
            <p className="text-xs text-zinc-500">敢说真话的 AI 助手</p>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = page === item.key
            return (
              <button
                key={item.key}
                onClick={() => {
                  if (item.key === 'settings') {
                    setSettingsOpen(true)
                  } else {
                    setPage(item.key)
                  }
                }}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-sm font-medium ${
                  isActive
                    ? 'bg-black text-white shadow-md'
                    : 'text-zinc-700 hover:bg-black/5'
                }`}
              >
                <Icon size={18} className={isActive ? '' : item.color} />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>

        <div className="p-4 border-t border-black/5 text-xs text-zinc-500">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span>服务运行中</span>
          </div>
          <div className="mt-1.5 text-zinc-400">v0.9.8</div>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden relative z-0">
        {page === 'chat' && <ChatPage />}
        {page === 'resources' && <ResourcesPage />}
        {page === 'profile' && <ProfilePage />}
      </main>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  )
}
