import { Leaf, Bell, Settings, Shield } from 'lucide-react'
import { APP_NAME, APP_VERSION } from '@/lib/constants'

export function Navbar() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-14 items-center px-6 gap-4">
        {/* Brand */}
        <div className="flex items-center gap-2 font-semibold select-none">
          <div className="flex items-center justify-center h-7 w-7 rounded-md bg-primary">
            <Leaf className="h-4 w-4 text-primary-foreground" />
          </div>
          <span className="text-primary font-bold tracking-tight">{APP_NAME}</span>
          <span className="text-xs text-muted-foreground font-normal hidden sm:inline">
            v{APP_VERSION}
          </span>
        </div>

        <div className="flex-1" />

        {/* System trust indicator */}
        <div className="hidden md:flex items-center gap-1.5 text-xs text-muted-foreground border rounded-full px-3 py-1">
          <Shield className="h-3 w-3 text-primary" />
          <span>Deterministic engine active</span>
        </div>

        <nav className="flex items-center gap-1">
          <button
            className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground h-9 w-9"
            aria-label="Notifications"
          >
            <Bell className="h-4 w-4" />
          </button>
          <button
            className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground h-9 w-9"
            aria-label="Settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        </nav>
      </div>
    </header>
  )
}
