import { useState, useCallback } from 'react'
import { useUpload } from '../api'
import { Upload as UploadIcon, FileUp, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'

const SOURCE_TYPES = [
  { value: 'sap_fuel', label: 'SAP Fuel & Procurement', desc: 'CSV/XLSX from SAP SE16N / SQVI extract (EKKO/EKPO/MSEG shape)' },
  { value: 'utility_electricity', label: 'Utility Electricity', desc: 'Monthly billing CSV from utility portal (ConEd, PG&E, etc.)' },
  { value: 'travel_concur', label: 'Corporate Travel (Concur)', desc: 'Concur Standard Reporting CSV (air/hotel/car segments)' },
]

export default function UploadPage() {
  const [sourceType, setSourceType] = useState('sap_fuel')
  const [dragActive, setDragActive] = useState(false)
  const [file, setFile] = useState(null)
  const upload = useUpload()

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setDragActive(false)
    const f = e.dataTransfer?.files?.[0] || e.target?.files?.[0]
    if (f) setFile(f)
  }, [])

  const handleSubmit = () => {
    if (!file) return
    upload.mutate({ file, sourceType })
  }

  return (
    <div className="p-8 max-w-2xl">
      <h2 className="text-xl font-semibold text-gray-900 mb-6">Upload Source Data</h2>

      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">Source Type</label>
        <div className="space-y-2">
          {SOURCE_TYPES.map(st => (
            <label key={st.value}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                sourceType === st.value ? 'border-emerald-500 bg-emerald-50' : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <input type="radio" name="source" value={st.value}
                checked={sourceType === st.value}
                onChange={() => setSourceType(st.value)}
                className="mt-0.5 accent-emerald-600"
              />
              <div>
                <p className="text-sm font-medium text-gray-900">{st.label}</p>
                <p className="text-xs text-gray-500">{st.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div
        className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
          dragActive ? 'border-emerald-400 bg-emerald-50' : 'border-gray-300 hover:border-gray-400'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
      >
        {file ? (
          <div className="flex items-center justify-center gap-3">
            <FileUp className="text-emerald-600" size={24} />
            <div className="text-left">
              <p className="text-sm font-medium text-gray-900">{file.name}</p>
              <p className="text-xs text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
            <button onClick={() => setFile(null)} className="ml-4 text-xs text-red-500 hover:text-red-700">Remove</button>
          </div>
        ) : (
          <>
            <UploadIcon className="mx-auto text-gray-400 mb-2" size={32} />
            <p className="text-sm text-gray-600 mb-1">Drag & drop your file here, or</p>
            <label className="inline-block px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 cursor-pointer hover:bg-gray-50">
              Browse
              <input type="file" className="hidden" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0])} />
            </label>
            <p className="text-xs text-gray-400 mt-2">Accepts CSV and XLSX files</p>
          </>
        )}
      </div>

      <button
        onClick={handleSubmit}
        disabled={!file || upload.isPending}
        className="mt-4 w-full py-2.5 px-4 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {upload.isPending ? <><Loader2 size={16} className="animate-spin" /> Parsing...</> : 'Upload & Parse'}
      </button>

      {upload.isSuccess && (
        <div className="mt-4 p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
          <div className="flex items-start gap-2">
            <CheckCircle className="text-emerald-600 mt-0.5" size={18} />
            <div>
              <p className="text-sm font-medium text-emerald-800">Upload successful</p>
              <p className="text-xs text-emerald-600 mt-1">
                {upload.data.row_count} rows parsed &middot; {upload.data.error_count} errors &middot;
                Status: {upload.data.status}
              </p>
              {upload.data.parse_summary && (
                <p className="text-xs text-emerald-600">
                  {upload.data.parse_summary.activities_created} activity records created
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {upload.isError && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-start gap-2">
            <AlertCircle className="text-red-600 mt-0.5" size={18} />
            <div>
              <p className="text-sm font-medium text-red-800">Upload failed</p>
              <p className="text-xs text-red-600 mt-1">{upload.error?.response?.data?.error || upload.error?.message}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
