import React from 'react'
import {NotAvailable, SchedulerTable, MonitoredEndpoints, HeartbeatsTable} from './SeoShared.jsx'

export default function SeoSentinelPanel({overview, status, error}) {
  if (!overview) {
    return (
      <div className="cs-diffs-table-wrap">
        {status === 'loading' ? <div style={{fontSize: 13, color: '#64748B'}}>Reading the SEO worker&apos;s persisted state…</div>
          : <NotAvailable title="Sentinel and scheduler state" reason={`${error || 'SEO worker unavailable'}.`} />}
      </div>
    )
  }
  return (
    <div className="cs-diffs-table-wrap">
      <SchedulerTable overview={overview} />
      <MonitoredEndpoints overview={overview} />
      <HeartbeatsTable overview={overview} />
    </div>
  )
}
