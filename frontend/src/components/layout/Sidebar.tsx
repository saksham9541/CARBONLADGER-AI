import {
  LayoutDashboard,
  Upload,
  BookOpen,
  FlaskConical,
  Calculator,
  BarChart3,
  FileText,
  AlertTriangle,
  Search,
  Settings,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'

const navGroups = [
  {
    label: 'Main',
    items: [
      { label: 'Dashboard', icon: LayoutDashboard, to: '/' },
    ],
  },
  {
    label: 'Evidence',
    items: [
      { label: 'Upload Evidence', icon: Upload, to: '/evidence' },
      { label: 'Source Ledger', icon: BookOpen, to: '/ledger' },
      { label: 'Exceptions', icon: AlertTriangle, to: '/exceptions' },
    ],
  },
  {
    label: 'Carbon Engine',
    items: [
      { label: 'Emission Factors', icon: FlaskConical, to: '/factors' },
      { label: 'Calculations', icon: Calculator, to: '/calculations' },
    ],
  },
  {
    label: 'Reporting',
    items: [
      { label: 'Analytics', icon: BarChart3, to: '/analytics' },
      { label: 'Reports', icon: FileText, to: '/reports' },
      { label: 'Audit Center', icon: Search, to: '/audit' },
    ],
  },
  {
    label: 'System',
    items: [
      { label: 'Settings', icon: Settings, to: '/settings' },
    ],
  },
]

export function Sidebar() {
  return (
    <aside className="w-56 border-r bg-muted/20 flex flex-col py-4 shrink-0 overflow-y-auto">
      {navGroups.map((group) => (
        <div key={group.label} className="mb-4">
          <p className="px-4 py-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            {group.label}
          </p>
          <nav className="flex flex-col gap-0.5 px-2">
            {group.items.map(({ label, icon: Icon, to }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      ))}
    </aside>
  )
}
