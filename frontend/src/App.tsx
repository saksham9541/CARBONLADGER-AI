import { Routes, Route } from 'react-router-dom'
import { Layout } from '@/components/layout/Layout'
import { Dashboard } from '@/pages/Dashboard'
import { NotFound } from '@/pages/NotFound'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        {/* Phase 2+ pages will be registered here */}
        <Route path="evidence" element={<NotFound />} />
        <Route path="ledger" element={<NotFound />} />
        <Route path="factors" element={<NotFound />} />
        <Route path="calculations" element={<NotFound />} />
        <Route path="analytics" element={<NotFound />} />
        <Route path="reports" element={<NotFound />} />
        <Route path="audit" element={<NotFound />} />
        <Route path="settings" element={<NotFound />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

export default App
