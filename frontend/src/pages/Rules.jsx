import { useState } from 'react'
import { useRules, useCreateRule } from '../api'
import { Plus, Loader2 } from 'lucide-react'

export default function Rules() {
  const { data: rules, isLoading } = useRules()
  const create = useCreateRule()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    source_type: 'sap_fuel',
    match_field: 'MATNR',
    match_pattern: '',
    mapped_activity_type: 'diesel',
    notes: '',
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    create.mutate(form, { onSuccess: () => { setShowForm(false); setForm(f => ({ ...f, match_pattern: '', notes: '' })) } })
  }

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Classification Rules</h2>
          <p className="text-sm text-gray-500 mt-1">Analyst-authored mapping rules. When a parser encounters a matching field value, it assigns the mapped activity type instead of using the built-in fallback chain.</p>
        </div>
        <button
          onClick={() => setShowForm(s => !s)}
          className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 flex items-center gap-2"
        >
          <Plus size={16} /> Add Rule
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-5 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Source Type</label>
              <select value={form.source_type} onChange={e => setForm(f => ({ ...f, source_type: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                <option value="sap_fuel">SAP Fuel</option>
                <option value="utility_electricity">Utility</option>
                <option value="travel_concur">Travel</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Match Field</label>
              <input value={form.match_field} onChange={e => setForm(f => ({ ...f, match_field: e.target.value }))}
                placeholder="e.g. MATNR, MATKL, SAKTO"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Match Pattern (exact, case-insensitive)</label>
              <input value={form.match_pattern} onChange={e => setForm(f => ({ ...f, match_pattern: e.target.value }))}
                placeholder="e.g. MAT-MISC, 400100"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" required />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Mapped Activity Type</label>
              <select value={form.mapped_activity_type} onChange={e => setForm(f => ({ ...f, mapped_activity_type: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                <option value="diesel">diesel</option>
                <option value="petrol">petrol</option>
                <option value="lpg">lpg</option>
                <option value="natural_gas_m3">natural gas</option>
                <option value="heating_oil">heating oil</option>
                <option value="electricity_grid">electricity grid</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Notes (optional)</label>
            <input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={create.isPending}
              className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50">
              {create.isPending ? 'Saving...' : 'Save Rule'}
            </button>
            <button type="button" onClick={() => setShowForm(false)}
              className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50">
              Cancel
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="animate-spin text-gray-400" /></div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500">Source</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500">Match Field</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500">Pattern</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500">Maps To</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500">Notes</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(rules || []).map(r => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-600">{r.source_type?.replace(/_/g, ' ')}</td>
                  <td className="px-4 py-3 font-mono text-gray-900">{r.match_field}</td>
                  <td className="px-4 py-3 font-mono text-gray-900">{r.match_pattern}</td>
                  <td className="px-4 py-3 font-medium text-emerald-700">{r.mapped_activity_type}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{r.notes || '-'}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${r.active ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
                      {r.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                </tr>
              ))}
              {(!rules || rules.length === 0) && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">No classification rules yet. Add one to teach the parser new mappings.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
