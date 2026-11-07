import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Leaf } from 'lucide-react'

export function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 text-center">
      <div className="flex items-center justify-center h-20 w-20 rounded-2xl bg-muted">
        <Leaf className="h-10 w-10 text-muted-foreground" />
      </div>
      <div>
        <h1 className="text-4xl font-bold">Coming Soon</h1>
        <p className="text-muted-foreground max-w-md mt-2">
          This page is planned for a future phase. CarbonLedger AI is built incrementally —
          each phase adds auditable, production-quality capability.
        </p>
      </div>
      <Button asChild>
        <Link to="/">Back to Dashboard</Link>
      </Button>
    </div>
  )
}
