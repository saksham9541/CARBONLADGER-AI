import { useHealthCheck } from '@/hooks/useHealthCheck'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Leaf, Zap, TrendingDown, AlertCircle, CheckCircle2,
  Clock, Upload, BookOpen, Shield, ArrowRight,
} from 'lucide-react'
import { Link } from 'react-router-dom'

function StatusIcon({ status }: { status: 'ok' | 'degraded' | 'error' | 'loading' }) {
  if (status === 'ok') return <CheckCircle2 className="h-5 w-5 text-green-500" />
  if (status === 'degraded') return <AlertCircle className="h-5 w-5 text-yellow-500" />
  if (status === 'error') return <AlertCircle className="h-5 w-5 text-red-500" />
  return <Clock className="h-5 w-5 text-muted-foreground animate-spin" />
}

const statCards = [
  {
    title: 'Total Emissions',
    value: '—',
    unit: 'tCO₂e',
    description: 'No reporting period active',
    icon: Leaf,
    color: 'text-carbon-600',
  },
  {
    title: 'AI Extractions',
    value: '—',
    unit: 'records',
    description: 'No evidence uploaded yet',
    icon: Zap,
    color: 'text-blue-500',
  },
  {
    title: 'Evidence Coverage',
    value: '—',
    unit: '%',
    description: 'No billing intervals set',
    icon: TrendingDown,
    color: 'text-purple-500',
  },
]

const quickActions = [
  { label: 'Upload Evidence', icon: Upload, to: '/evidence', description: 'PDFs, images, Excel, audio' },
  { label: 'View Ledger', icon: BookOpen, to: '/ledger', description: 'Trace every activity record' },
  { label: 'Audit Center', icon: Shield, to: '/audit', description: 'Verify provenance & approvals' },
]

export function Dashboard() {
  const { health, loading, error } = useHealthCheck()

  const apiStatus: 'ok' | 'degraded' | 'error' | 'loading' = loading
    ? 'loading'
    : error
      ? 'error'
      : health?.status === 'ok'
        ? 'ok'
        : 'degraded'

  const badgeVariant = apiStatus === 'ok'
    ? 'success' as const
    : apiStatus === 'loading'
      ? 'secondary' as const
      : 'destructive' as const

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Page heading */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          CarbonLedger AI — Phase 1 initialized. Ready for evidence ingestion.
        </p>
      </div>

      {/* Core rule banner */}
      <Card className="border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-start gap-3">
            <Shield className="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
                Core Architectural Rule — AI never performs carbon arithmetic
              </p>
              <p className="text-xs text-amber-700 dark:text-amber-300 mt-0.5">
                All Scope 1/2/3 calculations, unit conversions, and emission factor lookups run
                exclusively in the Python backend using validated, versioned factor tables and{' '}
                <code className="font-mono">Decimal</code> precision.
                The frontend only displays results returned by the API.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* System health */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">System Status</CardTitle>
              <CardDescription>Backend API connectivity and service health</CardDescription>
            </div>
            <Badge variant={badgeVariant}>{apiStatus}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 mb-4">
            <StatusIcon status={apiStatus} />
            <div>
              <p className="text-sm font-medium">Backend API — FastAPI</p>
              <p className="text-xs text-muted-foreground">
                {loading && 'Checking connection to localhost:8000…'}
                {error && `Connection error: ${error}`}
                {health && `v${health.version} · ${health.environment} · ${new Date(health.timestamp).toLocaleTimeString()}`}
              </p>
            </div>
          </div>

          {health?.services && Object.keys(health.services).length > 0 && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries(health.services).map(([service, svcStatus]) => (
                <div key={service} className="flex items-center gap-2 rounded-md border p-2.5">
                  <div
                    className={`h-2 w-2 rounded-full shrink-0 ${
                      svcStatus === 'ok' ? 'bg-green-500' :
                      svcStatus === 'degraded' ? 'bg-yellow-500' :
                      svcStatus === 'unconfigured' ? 'bg-muted-foreground' : 'bg-red-500'
                    }`}
                  />
                  <span className="text-xs font-medium capitalize">{service}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* KPI stat cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {statCards.map(({ title, value, unit, description, icon: Icon, color }) => (
          <Card key={title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{title}</CardTitle>
              <Icon className={`h-4 w-4 ${color}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {value}{' '}
                <span className="text-sm font-normal text-muted-foreground">{unit}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">{description}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Quick Actions</h2>
        <div className="grid gap-3 md:grid-cols-3">
          {quickActions.map(({ label, icon: Icon, to, description }) => (
            <Card key={to} className="hover:shadow-md transition-shadow cursor-pointer">
              <CardContent className="pt-5 pb-5">
                <Link to={to} className="flex items-center gap-4">
                  <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-primary/10">
                    <Icon className="h-5 w-5 text-primary" />
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-sm">{label}</p>
                    <p className="text-xs text-muted-foreground">{description}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Phase indicator */}
      <Card className="border-dashed">
        <CardContent className="pt-5 pb-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Build Progress</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Phase 1 of 6 complete — Project initialization &amp; architecture
              </p>
            </div>
            <Button variant="outline" size="sm" asChild>
              <Link to="/audit">View Audit Trail</Link>
            </Button>
          </div>
          <div className="mt-3 w-full h-2 rounded-full bg-muted overflow-hidden">
            <div className="h-full bg-primary rounded-full" style={{ width: '16.6%' }} />
          </div>
          <div className="mt-1.5 flex justify-between text-[10px] text-muted-foreground">
            <span>Phase 1</span>
            <span>Phase 6</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
