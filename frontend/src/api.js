import axios from 'axios'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

const API_BASE = import.meta.env.VITE_API_URL || '/api'
const api = axios.create({ baseURL: API_BASE })

// Batches
export function useBatches() {
  return useQuery({
    queryKey: ['batches'],
    queryFn: () => api.get('/batches/').then(r => r.data.results ?? r.data),
  })
}

export function useUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, sourceType }) => {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('source_type', sourceType)
      return api.post('/batches/upload/', fd).then(r => r.data)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['batches'] })
      qc.invalidateQueries({ queryKey: ['records'] })
      qc.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

// Records
export function useRecords(params = {}) {
  return useQuery({
    queryKey: ['records', params],
    queryFn: () => api.get('/records/', { params }).then(r => r.data),
  })
}

export function useSummary() {
  return useQuery({
    queryKey: ['summary'],
    queryFn: () => api.get('/records/summary/').then(r => r.data),
  })
}

export function useApprove() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => api.post(`/records/${id}/approve/`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['records'] })
      qc.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useReject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, notes }) => api.post(`/records/${id}/reject/`, { notes }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['records'] })
      qc.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useBulkApprove() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids) => api.post('/records/bulk-approve/', { record_ids: ids }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['records'] })
      qc.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

export function useUpdateRecord() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }) => api.patch(`/records/${id}/`, data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['records'] })
      qc.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}

// Audit
export function useAuditEvents(params = {}) {
  return useQuery({
    queryKey: ['audit', params],
    queryFn: () => api.get('/audit/', { params }).then(r => r.data.results ?? r.data),
    enabled: !!params.object_id,
  })
}

// Rules
export function useRules() {
  return useQuery({
    queryKey: ['rules'],
    queryFn: () => api.get('/rules/').then(r => r.data.results ?? r.data),
  })
}

export function useCreateRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => api.post('/rules/', data).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  })
}
