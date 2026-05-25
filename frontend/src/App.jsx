import { Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, Upload, ClipboardCheck, Settings } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import UploadPage from './pages/Upload'
import Review from './pages/Review'
import Rules from './pages/Rules'

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/upload', icon: Upload, label: 'Upload' },
  { to: '/review', icon: ClipboardCheck, label: 'Review' },
  { to: '/rules', icon: Settings, label: 'Rules' },
]

export default function App() {
  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="w-56 bg-white border-r border-gray-200 flex flex-col">
        <div className="px-5 py-4 border-b border-gray-200">
          <h1 className="text-lg font-semibold text-gray-900">Carbon Ledger</h1>
          <p className="text-xs text-gray-500">Breathe ESG Prototype</p>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-3 border-t border-gray-200 text-xs text-gray-400">
          Demo Industries Ltd.
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/review" element={<Review />} />
          <Route path="/rules" element={<Rules />} />
        </Routes>
      </main>
    </div>
  )
}
