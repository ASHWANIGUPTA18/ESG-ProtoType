import { useState } from 'react'
import { useRecords, useApprove, useReject, useBulkApprove, useUpdateRecord, useAuditEvents } from '../api'
import { CheckCircle, XCircle, AlertTriangle, Clock, ChevronRight, X, Loader2, Edit3, History } from 'lucide-react'

const STATUS_CONFIG = {
  pending: { icon: Clock, color: 'bg-amber-50 text-amber-700 border-amber-200', label: 'Pending' },
  flagged: { icon: AlertTriangle, color: 'bg-red-50 text-red-700 border-red-200', label: 'Flagged' },
  approved: { icon: CheckCircle, color: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'Approved' },
  rejected: { icon: XCircle, color: 'bg-gray-100 text-gray-500 border-gray-200', label: 'Rejected' },
  edited: { icon: Edit3, color: 'bg-blue-50 text-blue-700 border-blue-200', label: 'Edited' },
}

const SCOPE_SHORT = { 1: 'S1', 2: 'S2', 3: 'S3' }

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.color}`}>
      <Icon size={12} />
      {cfg.label}
    </span>
  )
}

function AuditTrail({ recordId }) {
  const { data: events, isLoading } = useAuditEvents({
    object_id: recordId,
    content_type__model: 'activityrecord',
  })

  if (isLoading) return <div className="flex justify-center py-2"><Loader2 size={14} className="animate-spin text-gray-400" /></div>
  if (!events || events.length === 0) return <p className="text-xs text-gray-400">No audit events</p>

  const ACTION_STYLES = {
    parser_emit: 'bg-gray-100 text-gray-600',
    approve: 'bg-emerald-50 text-emerald-700',
    bulk_approve: 'bg-emerald-50 text-emerald-700',
    reject: 'bg-red-50 text-red-700',
    edit: 'bg-blue-50 text-blue-700',
    flag: 'bg-amber-50 text-amber-700',
    create: 'bg-gray-100 text-gray-600',
  }

  return (
    <div className="space-y-2">
      {events.map(ev => (
        <div key={ev.id} className="flex items-start gap-2 text-xs">
          <div className="w-1.5 h-1.5 rounded-full bg-gray-300 mt-1.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${ACTION_STYLES[ev.action] || 'bg-gray-100 text-gray-600'}`}>
                {ev.action.replace(/_/g, ' ')}
              </span>
              <span className="text-gray-500">by {ev.actor_name}</span>
            </div>
            <p className="text-gray-400 mt-0.5">{new Date(ev.ts).toLocaleString()}</p>
            {ev.notes && <p className="text-gray-500 mt-0.5">{ev.notes}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}

function RecordDrawer({ record, onClose }) {
  const approve = useApprove()
  const reject = useReject()
  const update = useUpdateRecord()
  const [editing, setEditing] = useState(null)
  const [editVal, setEditVal] = useState('')
  const [showAudit, setShowAudit] = useState(false)

  if (!record) return null

  const r = record
  const kg = r.emission_result?.kgco2e
  const flags = r.confidence_flags || []

  const startEdit = (field, val) => { setEditing(field); setEditVal(String(val ?? '')) }
  const saveEdit = () => {
    if (!editing) return
    update.mutate({ id: r.id, [editing]: editVal })
    setEditing(null)
  }

  return (
    <div className="fixed inset-y-0 right-0 w-[480px] bg-white border-l border-gray-200 shadow-xl z-50 flex flex-col">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
        <h3 className="text-base font-semibold text-gray-900">Record #{r.id}</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
      </div>

      <div className="flex-1 overflow-auto p-5 space-y-5">
        <div className="flex items-center gap-3">
          <StatusBadge status={r.status} />
          <span className="px-2 py-0.5 rounded bg-gray-100 text-xs font-medium text-gray-600">
            {SCOPE_SHORT[r.scope]} &middot; {r.ghg_category}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          {[
            ['Activity Type', 'activity_type', r.activity_type],
            ['Quantity', 'quantity', `${r.quantity} ${r.unit_canonical}`],
            ['Period', null, `${r.period_start} to ${r.period_end}`],
            ['Location', 'location_country', `${r.location_country || '-'} / ${r.location_region || '-'}`],
            ['Cost', null, r.cost ? `${r.cost} ${r.currency}` : '-'],
            ['Emissions', null, kg ? `${parseFloat(kg).toFixed(2)} kgCO2e` : 'No factor'],
          ].map(([label, field, val]) => (
            <div key={label}>
              <p className="text-xs text-gray-500">{label}</p>
              <div className="flex items-center gap-1">
                {editing === field ? (
                  <div className="flex gap-1">
                    <input value={editVal} onChange={e => setEditVal(e.target.value)} className="text-sm border rounded px-1 w-24" autoFocus />
                    <button onClick={saveEdit} className="text-xs text-emerald-600">Save</button>
                    <button onClick={() => setEditing(null)} className="text-xs text-gray-400">Cancel</button>
                  </div>
                ) : (
                  <>
                    <p className="font-medium text-gray-900">{val}</p>
                    {field && r.status !== 'approved' && (
                      <button onClick={() => startEdit(field, r[field])} className="text-gray-400 hover:text-gray-600"><Edit3 size={12} /></button>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        {flags.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-2">Confidence Flags</p>
            <div className="space-y-1">
              {flags.map((f, i) => (
                <div key={i} className={`px-3 py-2 rounded-lg text-xs ${
                  f.severity === 'error' ? 'bg-red-50 text-red-700' :
                  f.severity === 'info' ? 'bg-blue-50 text-blue-700' : 'bg-amber-50 text-amber-700'
                }`}>
                  <span className="font-medium">{f.code?.replace(/_/g, ' ')}</span>
                  {f.message && <span className="ml-1">&mdash; {f.message}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {r.details && Object.keys(r.details).length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-2">Source Details</p>
            <div className="bg-gray-50 rounded-lg p-3 text-xs font-mono max-h-48 overflow-auto">
              {Object.entries(r.details).filter(([, v]) => v).map(([k, v]) => (
                <div key={k} className="flex gap-2 py-0.5">
                  <span className="text-gray-500 w-36 shrink-0">{k}</span>
                  <span className="text-gray-900">{String(v)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {r.source_row_raw && (
          <div>
            <p className="text-xs text-gray-500 mb-2">Raw Source Row (line {r.source_row_line_no})</p>
            <pre className="bg-gray-50 rounded-lg p-3 text-xs font-mono max-h-40 overflow-auto whitespace-pre-wrap">
              {JSON.stringify(r.source_row_raw, null, 2)}
            </pre>
          </div>
        )}

        <div>
          <button
            onClick={() => setShowAudit(a => !a)}
            className="flex items-center gap-2 text-xs font-medium text-gray-500 hover:text-gray-700"
          >
            <History size={14} />
            {showAudit ? 'Hide' : 'Show'} Audit Trail
          </button>
          {showAudit && (
            <div className="mt-2">
              <AuditTrail recordId={r.id} />
            </div>
          )}
        </div>
      </div>

      {r.status !== 'approved' && (
        <div className="px-5 py-3 border-t border-gray-200 flex gap-2">
          <button
            onClick={() => approve.mutate(r.id)}
            disabled={approve.isPending}
            className="flex-1 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
          >
            {approve.isPending ? 'Approving...' : 'Approve'}
          </button>
          <button
            onClick={() => reject.mutate({ id: r.id, notes: '' })}
            disabled={reject.isPending}
            className="flex-1 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  )
}

export default function Review() {
  const [filters, setFilters] = useState({ page: 1 })
  const [selected, setSelected] = useState(new Set())
  const [activeRecord, setActiveRecord] = useState(null)
  const bulkApprove = useBulkApprove()

  const params = {
    page: filters.page,
    ...(filters.status && { status: filters.status }),
    ...(filters.scope && { scope: filters.scope }),
    ...(filters.source_type && { source_batch__source_type: filters.source_type }),
    ordering: filters.ordering || '-created_at',
  }
  const { data, isLoading } = useRecords(params)
  const records = data?.results ?? []
  const totalPages = data?.count ? Math.ceil(data.count / 50) : 1

  const toggleSelect = (id) => {
    const next = new Set(selected)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelected(next)
  }

  const toggleAll = () => {
    if (selected.size === records.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(records.map(r => r.id)))
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-gray-900">Review Records</h2>
        {selected.size > 0 && (
          <button
            onClick={() => { bulkApprove.mutate([...selected]); setSelected(new Set()) }}
            disabled={bulkApprove.isPending}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
          >
            {bulkApprove.isPending ? 'Approving...' : `Approve ${selected.size} selected`}
          </button>
        )}
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {['', 'pending', 'flagged', 'approved', 'rejected', 'edited'].map(s => (
          <button key={s}
            onClick={() => setFilters(f => ({ ...f, status: s || undefined, page: 1 }))}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              (filters.status || '') === s ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
            }`}
          >
            {s || 'All'}
          </button>
        ))}
        <span className="border-l border-gray-200 mx-1" />
        {[
          ['', 'All Sources'],
          ['sap_fuel', 'SAP'],
          ['utility_electricity', 'Utility'],
          ['travel_concur', 'Travel'],
        ].map(([v, l]) => (
          <button key={v}
            onClick={() => setFilters(f => ({ ...f, source_type: v || undefined, page: 1 }))}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              (filters.source_type || '') === v ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
            }`}
          >
            {l}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="animate-spin text-gray-400" /></div>
      ) : (
        <>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="w-10 px-3 py-3">
                    <input type="checkbox" checked={selected.size === records.length && records.length > 0} onChange={toggleAll} className="accent-emerald-600" />
                  </th>
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-500">Status</th>
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-500">Scope</th>
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-500">Activity Type</th>
                  <th className="text-right px-3 py-3 text-xs font-medium text-gray-500">Quantity</th>
                  <th className="text-right px-3 py-3 text-xs font-medium text-gray-500">kgCO2e</th>
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-500">Period</th>
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-500">Source</th>
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-500">Flags</th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {records.map(r => {
                  const kg = r.emission_result?.kgco2e
                  const flagCount = (r.confidence_flags || []).length
                  return (
                    <tr key={r.id}
                      className={`hover:bg-gray-50 cursor-pointer transition-colors ${selected.has(r.id) ? 'bg-emerald-50/50' : ''}`}
                      onClick={() => setActiveRecord(r)}
                    >
                      <td className="px-3 py-2.5" onClick={e => e.stopPropagation()}>
                        <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} className="accent-emerald-600" />
                      </td>
                      <td className="px-3 py-2.5"><StatusBadge status={r.status} /></td>
                      <td className="px-3 py-2.5 text-xs font-medium text-gray-600">{SCOPE_SHORT[r.scope]}</td>
                      <td className="px-3 py-2.5 font-medium text-gray-900">{r.activity_type.replace(/_/g, ' ')}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-900">{parseFloat(r.quantity).toLocaleString()} {r.unit_canonical}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-gray-900">{kg ? parseFloat(kg).toFixed(1) : '-'}</td>
                      <td className="px-3 py-2.5 text-xs text-gray-500">{r.period_start}</td>
                      <td className="px-3 py-2.5 text-xs text-gray-500">{r.source_type?.replace(/_/g, ' ')}</td>
                      <td className="px-3 py-2.5">
                        {flagCount > 0 && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-50 text-amber-700">
                            <AlertTriangle size={10} /> {flagCount}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5"><ChevronRight size={16} className="text-gray-400" /></td>
                    </tr>
                  )
                })}
                {records.length === 0 && (
                  <tr><td colSpan={10} className="px-3 py-8 text-center text-gray-400">No records match your filters</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <p className="text-xs text-gray-500">{data?.count} total records</p>
              <div className="flex gap-1">
                {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => i + 1).map(p => (
                  <button key={p}
                    onClick={() => setFilters(f => ({ ...f, page: p }))}
                    className={`px-3 py-1 rounded text-xs font-medium ${
                      filters.page === p ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 border border-gray-200 hover:border-gray-400'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {activeRecord && <RecordDrawer record={activeRecord} onClose={() => setActiveRecord(null)} />}
    </div>
  )
}
