'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api, { getApiBaseUrl } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

export interface InvoiceDocument {
  id: string;
  original_filename: string;
  storage_path: string;
  mime_type: string;
  file_size: number;
  status: string;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
  raw_ocr_text: string | null;
  normalized_image_paths: string[] | null;
  extracted_fields?: ExtractedField[];
}

export interface PaginatedDocuments {
  items: InvoiceDocument[];
  total: number;
  total_pages: number;
  page: number;
  page_size: number;
}

export interface DocumentSession {
  id: string;
  document_id: string;
  current_stage: string;
  progress_percent: number;
  stage_history: Array<{
    stage: string;
    progress: number;
    timestamp: string;
    message: string;
  }>;
}

export interface ExtractedField {
  id: string;
  document_id: string;
  field_name: string;
  value: string;
  confidence: number;
  bbox: unknown;
  is_corrected: boolean;
  original_value: string | null;
  corrected_by: string | null;
  corrected_at: string | null;
}

export interface FraudFlag {
  id: string;
  document_id: string;
  flag_type: string;
  severity: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface DuplicateFlag {
  id: string;
  document_id: string;
  duplicate_of_document_id: string;
  match_type: string;
  confidence_score: number;
  created_at: string;
}

export interface RuleViolation {
  id: string;
  document_id: string;
  rule_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Rule {
  id: string;
  name: string;
  description: string | null;
  condition: Record<string, unknown>;
  severity: string;
  active: boolean;
}

export interface Vendor {
  id: string;
  canonical_name: string;
  aliases: string[];
  tax_id: string | null;
  is_approved: boolean;
  is_new: boolean;
  bank_account_last4: string | null;
  bank_account_hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  vendor_id: string;
  expected_amount: string;
  line_items: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
}

export interface GoodsReceipt {
  id: string;
  po_id: string;
  received_amount: string;
  received_at: string;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface ReviewQueueItem {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  status: string;
  uploaded_by: string;
  created_at: string;
  priority_score: number;
  min_confidence: number;
  max_fraud_severity: number;
  violation_count: number;
  duplicate_count: number;
  fraud_flag_types: string[];
}

export interface DocumentDetail extends InvoiceDocument {
  extracted_fields: ExtractedField[];
  fraud_flags: FraudFlag[];
  duplicate_flags: DuplicateFlag[];
  rule_violations: RuleViolation[];
  sessions: DocumentSession[];
}

export interface UploadResponse {
  document_id: string;
  status: string;
  message: string;
}

export interface ReviewDecision {
  action: 'verify' | 'flag' | 'confirm_duplicate';
  corrections?: Array<{ field_name: string; corrected_value: string }>;
  reason?: string;
}

export interface QueryResponse {
  answer: string;
  structured_data: Record<string, unknown> | null;
  intent: string;
  error: string | null;
}

const DOCUMENTS_PER_PAGE = 20;

export interface PaginatedDocuments {
  items: InvoiceDocument[];
  total: number;
  total_pages: number;
  page: number;
  page_size: number;
}

export function useDocuments({
  page = 1,
  status,
  uploaded_by,
  date_from,
  date_to,
  pageSize = 20,
}: {
  page?: number;
  status?: string;
  uploaded_by?: string;
  date_from?: string;
  date_to?: string;
  pageSize?: number;
} = {}) {
  return useQuery<PaginatedDocuments>({
    queryKey: ['documents', { page, status, uploaded_by, date_from, date_to, pageSize }],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('page', page.toString());
      params.append('page_size', pageSize.toString());
      if (status) params.append('status', status);
      if (uploaded_by) params.append('uploaded_by', uploaded_by);
      if (date_from) params.append('date_from', date_from);
      if (date_to) params.append('date_to', date_to);

      const response = await api.get(`/documents?${params.toString()}`);
      return response.data;
    },
    staleTime: 30000,
  });
}

export function useDocument(id: string, enabled = true) {
  return useQuery({
    queryKey: ['document', id],
    queryFn: async () => {
      const response = await api.get(`/documents/${id}`);
      return response.data;
    },
    enabled: enabled && !!id,
    staleTime: 30000,
  });
}

export function useDocumentSession(id: string, enabled = true) {
  return useQuery({
    queryKey: ['documentSession', id],
    queryFn: async () => {
      const response = await api.get(`/documents/${id}/session`);
      return response.data;
    },
    enabled: enabled && !!id,
    staleTime: 15000,
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);

      const response = await api.post('/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
  });
}

export function useDocumentSessionPolling(documentId: string, enabled = true) {
  return useQuery({
    queryKey: ['documentSession', documentId],
    queryFn: async () => {
      const response = await api.get(`/documents/${documentId}/session`);
      return response.data;
    },
    enabled: enabled && !!documentId,
    refetchInterval: 1500,
    staleTime: 1000,
  });
}

export function useReviewQueue({
  status,
  page = 1,
  pageSize = 20,
}: {
  status?: string[];
  page?: number;
  pageSize?: number;
} = {}) {
  return useQuery({
    queryKey: ['reviewQueue', { status, page, pageSize }],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('page', page.toString());
      params.append('page_size', pageSize.toString());
      if (status?.length) {
        status.forEach((s) => params.append('status', s));
      }
      const response = await api.get(`/documents/review-queue?${params.toString()}`);
      return response.data;
    },
    staleTime: 15000,
  });
}

export function useReviewDocument(id: string, enabled = true) {
  return useQuery({
    queryKey: ['reviewDocument', id],
    queryFn: async () => {
      const response = await api.get(`/documents/${id}/review`);
      return response.data;
    },
    enabled: enabled && !!id,
    staleTime: 15000,
  });
}

export function useSubmitReview() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ documentId, decision }: { documentId: string; decision: { action: 'verify' | 'flag' | 'confirm_duplicate'; corrections?: Array<{ field_name: string; corrected_value: string }>; reason?: string } }) => {
      const response = await api.patch(`/documents/${documentId}/review`, decision);
      return response.data;
    },
    onSuccess: (_, { documentId }) => {
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] });
      queryClient.invalidateQueries({ queryKey: ['reviewDocument', documentId] });
      queryClient.invalidateQueries({ queryKey: ['document', documentId] });
    },
  });
}

export function useDocumentFile(id: string) {
  return `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/documents/${id}/file`;
}

export function useNLQuery() {
  return useMutation({
    mutationFn: async (question: string) => {
      const response = await api.post('/nl-query/query', { question });
      return response.data;
    },
  });
}

export function useRules() {
  return useQuery({
    queryKey: ['rules'],
    queryFn: async () => {
      const response = await api.get('/rules');
      return response.data;
    },
    staleTime: 60000,
  });
}

export function useCreateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (rule: { name: string; description?: string; condition: Record<string, unknown>; severity: string }) => {
      const response = await api.post('/rules', rule);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] });
    },
  });
}

export function useUpdateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...rule }: { id: string; name?: string; description?: string; condition?: Record<string, unknown>; severity?: string; active?: boolean }) => {
      const response = await api.patch(`/rules/${id}`, rule);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] });
    },
  });
}

export function useDeleteRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/rules/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] });
    },
  });
}

export function useTier() {
  return useQuery({
    queryKey: ['tier'],
    queryFn: async () => {
      // NOTE: the tier endpoint lives at /system/tier, intentionally OUTSIDE
      // the /api/v1 prefix, so it must bypass the axios baseURL (/api/v1).
      const response = await api.get(`${getApiBaseUrl()}/system/tier`);
      return response.data;
    },
    staleTime: 60000,
  });
}

export function usePurchaseOrders() {
  return useQuery({
    queryKey: ['purchaseOrders'],
    queryFn: async () => {
      const response = await api.get('/purchase-orders');
      return response.data;
    },
    staleTime: 60000,
  });
}

export function useCreatePurchaseOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (po: { po_number: string; vendor_id: string; expected_amount: string; line_items: Record<string, unknown>[] }) => {
      const response = await api.post('/purchase-orders', po);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['purchaseOrders'] });
    },
  });
}

export function useGoodsReceipts(poId: string) {
  return useQuery({
    queryKey: ['goodsReceipts', poId],
    queryFn: async () => {
      const response = await api.get(`/purchase-orders/${poId}/goods-receipts`);
      return response.data;
    },
    enabled: !!poId,
    staleTime: 60000,
  });
}

export function useCreateGoodsReceipt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (receipt: { po_id: string; received_amount: string; received_at: string }) => {
      const response = await api.post('/purchase-orders/goods-receipts', receipt);
      return response.data;
    },
    onSuccess: (_, { po_id }) => {
      queryClient.invalidateQueries({ queryKey: ['goodsReceipts', po_id] });
    },
  });
}

export interface Document {
  id: string;
  original_filename: string;
  storage_path: string;
  mime_type: string;
  file_size: number;
  status: string;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
  raw_ocr_text: string | null;
  normalized_image_paths: string[] | null;
}

export interface DocumentSession {
  id: string;
  document_id: string;
  current_stage: string;
  progress_percent: number;
  stage_history: Array<{
    stage: string;
    progress: number;
    timestamp: string;
    message: string;
  }>;
}

export interface ExtractedField {
  id: string;
  document_id: string;
  field_name: string;
  value: string;
  confidence: number;
  bbox: unknown;
  is_corrected: boolean;
  original_value: string | null;
  corrected_by: string | null;
  corrected_at: string | null;
}

export interface FraudFlag {
  id: string;
  document_id: string;
  flag_type: string;
  severity: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface DuplicateFlag {
  id: string;
  document_id: string;
  duplicate_of_document_id: string;
  match_type: string;
  confidence_score: number;
  created_at: string;
}

export interface RuleViolation {
  id: string;
  document_id: string;
  rule_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Rule {
  id: string;
  name: string;
  description: string | null;
  condition: Record<string, unknown>;
  severity: string;
  active: boolean;
}

export interface Vendor {
  id: string;
  canonical_name: string;
  aliases: string[];
  tax_id: string | null;
  is_approved: boolean;
  is_new: boolean;
  bank_account_last4: string | null;
  bank_account_hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  vendor_id: string;
  expected_amount: string;
  line_items: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
}

export interface GoodsReceipt {
  id: string;
  po_id: string;
  received_amount: string;
  received_at: string;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface ReviewQueueItem {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  status: string;
  uploaded_by: string;
  created_at: string;
  priority_score: number;
  min_confidence: number;
  max_fraud_severity: number;
  violation_count: number;
  duplicate_count: number;
  fraud_flag_types: string[];
}

export interface DocumentDetail extends InvoiceDocument {
  extracted_fields: ExtractedField[];
  fraud_flags: FraudFlag[];
  duplicate_flags: DuplicateFlag[];
  rule_violations: RuleViolation[];
  sessions: DocumentSession[];
}

export interface UploadResponse {
  document_id: string;
  status: string;
  message: string;
}

export interface ReviewDecision {
  action: 'verify' | 'flag' | 'confirm_duplicate';
  corrections?: Array<{ field_name: string; corrected_value: string }>;
  reason?: string;
}

export interface QueryResponse {
  answer: string;
  structured_data: Record<string, unknown> | null;
  intent: string;
  error: string | null;
}

export interface ExtractedField {
  id: string;
  document_id: string;
  field_name: string;
  value: string;
  confidence: number;
  bbox: unknown;
  is_corrected: boolean;
  original_value: string | null;
  corrected_by: string | null;
  corrected_at: string | null;
}

export interface FraudFlag {
  id: string;
  document_id: string;
  flag_type: string;
  severity: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface DuplicateFlag {
  id: string;
  document_id: string;
  duplicate_of_document_id: string;
  match_type: string;
  confidence_score: number;
  created_at: string;
}

export interface RuleViolation {
  id: string;
  document_id: string;
  rule_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Rule {
  id: string;
  name: string;
  description: string | null;
  condition: Record<string, unknown>;
  severity: string;
  active: boolean;
}

export interface Vendor {
  id: string;
  canonical_name: string;
  aliases: string[];
  tax_id: string | null;
  is_approved: boolean;
  is_new: boolean;
  bank_account_last4: string | null;
  bank_account_hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  vendor_id: string;
  expected_amount: string;
  line_items: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
}

export interface GoodsReceipt {
  id: string;
  po_id: string;
  received_amount: string;
  received_at: string;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface ReviewQueueItem {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  status: string;
  uploaded_by: string;
  created_at: string;
  priority_score: number;
  min_confidence: number;
  max_fraud_severity: number;
  violation_count: number;
  duplicate_count: number;
  fraud_flag_types: string[];
}

export interface DocumentDetail extends InvoiceDocument {
  extracted_fields: ExtractedField[];
  fraud_flags: FraudFlag[];
  duplicate_flags: DuplicateFlag[];
  rule_violations: RuleViolation[];
  sessions: DocumentSession[];
}

export interface UploadResponse {
  document_id: string;
  status: string;
  message: string;
}

export interface ReviewDecision {
  action: 'verify' | 'flag' | 'confirm_duplicate';
  corrections?: Array<{ field_name: string; corrected_value: string }>;
  reason?: string;
}

export interface QueryResponse {
  answer: string;
  structured_data: Record<string, unknown> | null;
  intent: string;
  error: string | null;
}

export interface ExtractedField {
  id: string;
  document_id: string;
  field_name: string;
  value: string;
  confidence: number;
  bbox: unknown;
  is_corrected: boolean;
  original_value: string | null;
  corrected_by: string | null;
  corrected_at: string | null;
}

export interface FraudFlag {
  id: string;
  document_id: string;
  flag_type: string;
  severity: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface DuplicateFlag {
  id: string;
  document_id: string;
  duplicate_of_document_id: string;
  match_type: string;
  confidence_score: number;
  created_at: string;
}

export interface RuleViolation {
  id: string;
  document_id: string;
  rule_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Rule {
  id: string;
  name: string;
  description: string | null;
  condition: Record<string, unknown>;
  severity: string;
  active: boolean;
}

export interface Vendor {
  id: string;
  canonical_name: string;
  aliases: string[];
  tax_id: string | null;
  is_approved: boolean;
  is_new: boolean;
  bank_account_last4: string | null;
  bank_account_hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  vendor_id: string;
  expected_amount: string;
  line_items: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
}

export interface GoodsReceipt {
  id: string;
  po_id: string;
  received_amount: string;
  received_at: string;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface ReviewQueueItem {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  status: string;
  uploaded_by: string;
  created_at: string;
  priority_score: number;
  min_confidence: number;
  max_fraud_severity: number;
  violation_count: number;
  duplicate_count: number;
  fraud_flag_types: string[];
}

export interface DocumentDetail extends InvoiceDocument {
  extracted_fields: ExtractedField[];
  fraud_flags: FraudFlag[];
  duplicate_flags: DuplicateFlag[];
  rule_violations: RuleViolation[];
  sessions: DocumentSession[];
}

export interface UploadResponse {
  document_id: string;
  status: string;
  message: string;
}

export interface ReviewDecision {
  action: 'verify' | 'flag' | 'confirm_duplicate';
  corrections?: Array<{ field_name: string; corrected_value: string }>;
  reason?: string;
}

export interface QueryResponse {
  answer: string;
  structured_data: Record<string, unknown> | null;
  intent: string;
  error: string | null;
}