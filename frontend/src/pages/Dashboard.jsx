import { useSummary, useBatches } from '../api'
import { AlertTriangle, CheckCircle, Clock, XCircle, Loader2, Download } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts'

const SCOPE_LABELS = { 1: 'Scope 1 (Fuel)', 2: 'Scope 2 (Electricity)', 3: 'Scope 3 (Travel)' }
const SCOPE_COLORS = { 1: '#f59e0b', 2: '#3b82f6', 3: '#10b981' }
const SOURCE_LABELS = { sap_fuel: 'SAP Fuel', utility_electricity: 'Utility', travel_concur: 'Travel' }
const SOURCE_COLORS = { sap_fuel: '#f59e0b', utility_electricity: '#3b82f6', travel_concur: '#10b981' }

function Stat({ label, value, icon: Icon, color }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-gray-500">{label}</p>
        {Icon && <Icon size={20} className={color} />}
      </div>
      <p className="mt-2 text-2xl font-bold text-gray-900">{value}</p>
    </div>
  )
}

export default function Dashboard() {
  const { data: summary, isLoading } = useSummary()
  const { data: batches } = useBatches()

  if (isLoading) return <div className="p-8 flex justify-center"><Loader2 className="animate-spin text-gray-400" /></div>
  if (!summary) return null

  const s = summary.by_status || {}
  const tco2e = (parseFloat(summary.total_kgco2e || 0) / 1000).toFixed(1)

  const scopeChartData = Object.entries(summary.scope_emissions || {}).map(([k, v]) => ({
    name: SCOPE_LABELS[k] || `Scope ${k}`,
    tCO2e: +(parseFloat(v) / 1000).toFixed(2),
    fill: SCOPE_COLORS[k] || '#6b7280',
  }))

  const sourceChartData = Object.entries(summary.source_emissions || {}).map(([k, v]) => ({
    name: SOURCE_LABELS[k] || k,
    tCO2e: +(parseFloat(v.kgco2e) / 1000).toFixed(2),
    records: v.count,
    fill: SOURCE_COLORS[k] || '#6b7280',
  }))

  const statusPieData = [
    { name: 'Pending', value: s.pending || 0, fill: '#f59e0b' },
    { name: 'Flagged', value: s.flagged || 0, fill: '#ef4444' },
    { name: 'Approved', value: s.approved || 0, fill: '#10b981' },
    { name: 'Rejected', value: s.rejected || 0, fill: '#6b7280' },
    { name: 'Edited', value: s.edited || 0, fill: '#3b82f6' },
  ].filter(d => d.value > 0)

  return (
    <div className="p-8 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-gray-900">Dashboard</h2>
        <a
          href="/api/records/export/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          <Download size={16} /> Export CSV
        </a>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        <Stat label="Total Records" value={summary.total_records} />
        <Stat label="Pending" value={s.pending || 0} icon={Clock} color="text-amber-500" />
        <Stat label="Flagged" value={s.flagged || 0} icon={AlertTriangle} color="text-red-500" />
        <Stat label="Approved" value={s.approved || 0} icon={CheckCircle} color="text-emerald-500" />
        <Stat label="Total Emissions" value={`${tco2e} tCO2e`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm font-medium text-gray-500 mb-4">Emissions by Scope (tCO2e)</p>
          {scopeChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={scopeChartData} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" tick={{ fontSize: 12 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={130} />
                <Tooltip formatter={(v) => [`${v} tCO2e`, 'Emissions']} />
                <Bar dataKey="tCO2e" radius={[0, 6, 6, 0]}>
                  {scopeChartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-400 py-8 text-center">No emission data yet</p>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm font-medium text-gray-500 mb-4">Review Status</p>
          {statusPieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={statusPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={50} outerRadius={85} paddingAngle={2}>
                  {statusPieData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                </Pie>
                <Tooltip />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-400 py-8 text-center">No records yet</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm font-medium text-gray-500 mb-4">Emissions by Source (tCO2e)</p>
          {sourceChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={sourceChartData} margin={{ left: 10 }}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v, name) => [name === 'tCO2e' ? `${v} tCO2e` : v, name === 'tCO2e' ? 'Emissions' : 'Records']} />
                <Bar dataKey="tCO2e" radius={[6, 6, 0, 0]}>
                  {sourceChartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-400 py-8 text-center">No emission data yet</p>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm font-medium text-gray-500 mb-3">By Scope (Records)</p>
          <div className="space-y-3">
            {Object.entries(summary.by_scope || {}).map(([k, v]) => {
              const pct = summary.total_records ? Math.round((v / summary.total_records) * 100) : 0
              return (
                <div key={k}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-600">{SCOPE_LABELS[k] || `Scope ${k}`}</span>
                    <span className="font-medium text-gray-900">{v} ({pct}%)</span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2">
                    <div className="h-2 rounded-full" style={{ width: `${pct}%`, backgroundColor: SCOPE_COLORS[k] || '#6b7280' }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {summary.flag_breakdown && Object.keys(summary.flag_breakdown).length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-8">
          <p className="text-sm font-medium text-gray-500 mb-3">Flags Requiring Attention</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(summary.flag_breakdown)
              .sort((a, b) => b[1] - a[1])
              .map(([code, count]) => (
                <span key={code} className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                  {code.replace(/_/g, ' ')}
                  <span className="bg-amber-200 text-amber-800 px-1.5 rounded-full">{count}</span>
                </span>
              ))}
          </div>
        </div>
      )}

      {batches && batches.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm font-medium text-gray-500 mb-3">Recent Uploads</p>
          <div className="divide-y divide-gray-100">
            {batches.slice(0, 5).map(b => (
              <div key={b.id} className="py-2 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-900">{b.original_filename}</p>
                  <p className="text-xs text-gray-500">{b.source_type.replace(/_/g, ' ')} &middot; {new Date(b.uploaded_at).toLocaleDateString()}</p>
                </div>
                <div className="text-right">
                  <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                    b.status === 'completed' ? 'bg-emerald-50 text-emerald-700' :
                    b.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-600'
                  }`}>{b.status}</span>
                  <p className="text-xs text-gray-500 mt-0.5">{b.row_count} rows</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
