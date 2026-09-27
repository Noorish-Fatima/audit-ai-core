'use client';

import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useDocuments, useTier, InvoiceDocument } from '@/hooks/useQueries';
import { useAuth } from '@/contexts/AuthContext';
import { Search, Filter, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Download, Eye, MoreHorizontal, Shield, AlertTriangle, Copy } from 'lucide-react';
import clsx from 'clsx';
import { format } from 'date-fns';

function DocumentsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { data: tier } = useTier();
  const [statusFilter, setStatusFilter] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sortBy, setSortBy] = useState<'date' | 'status' | 'filename'>('date');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  const enabledFeatures = tier?.features || {};

  const { data: documentsData, isLoading, refetch } = useDocuments({
    page,
    status: statusFilter.length > 0 ? statusFilter.join(',') : undefined,
    pageSize,
  });

  const handleSort = (field: 'date' | 'status' | 'filename') => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  const statusOptions = [
    { value: 'pending', label: 'Pending' },
    { value: 'ocr_processing', label: 'OCR Processing' },
    { value: 'extracting', label: 'Extracting' },
    { value: 'validating', label: 'Validating' },
    { value: 'review', label: 'Review' },
    { value: 'verified', label: 'Verified' },
    { value: 'flagged', label: 'Flagged' },
    { value: 'duplicate', label: 'Duplicate' },
  ];

  const statusColors = {
    pending: 'badge-warning',
    ocr_processing: 'badge-primary',
    extracting: 'badge-primary',
    validating: 'badge-primary',
    review: 'badge-warning',
    verified: 'badge-success',
    flagged: 'badge-danger',
    duplicate: 'badge-danger',
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="top-bar">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-900">Documents</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-600 hidden sm:block">
            All documents in the system
          </span>
        </div>
      </header>

      <div className="flex">
        {/* Filters Sidebar */}
        <aside className="w-72 bg-white border-r border-slate-200 flex flex-col h-[calc(100vh-64px)] overflow-y-auto lg:block hidden">
          <div className="p-4 border-b border-slate-200">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-900">Filters</h3>
            </div>
          </div>

          <div className="p-4">
            {/* Search */}
            <div className="mb-4">
              <label className="label">Search</label>
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l4.35 4.35"/></svg>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search filename..."
                  className="input pl-10"
                />
              </div>
            </div>

            {/* Status Filter */}
            <div className="mb-4">
              <label className="label">Status</label>
              <div className="space-y-2">
                {statusOptions.map((opt) => (
                  <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={statusFilter.includes(opt.value)}
                      onChange={(e) => setStatusFilter(e.target.checked ? [...statusFilter, opt.value] : statusFilter.filter(s => s !== opt.value))}
                      className="w-4 h-4 text-primary-600 border-slate-300 rounded focus:ring-primary-500"
                    />
                    <span className="text-sm text-slate-700 capitalize">{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 overflow-auto">
          {/* Toolbar */}
          <div className="toolbar">
            <div className="toolbar-group">
              <h2 className="text-lg font-semibold text-slate-900">Documents</h2>
              <span className="px-2 py-0.5 bg-slate-100 text-slate-600 text-sm rounded">
                {documentsData?.total || 0} documents
              </span>
            </div>
            <div className="toolbar-group ml-auto">
              <select
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                className="input w-auto"
              >
                <option value={10}>10 per page</option>
                <option value={20}>20 per page</option>
                <option value={50}>50 per page</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th onClick={() => handleSort('filename')} className="cursor-pointer select-none">
                    <div className="flex items-center gap-1">
                      Filename
                      {sortBy === 'filename' && (sortOrder === 'asc' ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />)}
                    </div>
                  </th>
                  <th onClick={() => handleSort('date')} className="cursor-pointer select-none">
                    <div className="flex items-center gap-1">
                      Date
                      {sortBy === 'date' && (sortOrder === 'asc' ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />)}
                    </div>
                  </th>
                  <th onClick={() => handleSort('status')} className="cursor-pointer select-none">
                    <div className="flex items-center gap-1">
                      Status
                      {sortBy === 'status' && (sortOrder === 'asc' ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />)}
                    </div>
                  </th>
                  <th>Vendor</th>
                  <th>Size</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
<tbody>
                {isLoading ? (
                  <>
                    <tr key="loading">
                      <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                        <div className="flex flex-col items-center gap-3">
                          <div className="w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full animate-spin" />
                          <span className="text-sm">Loading documents...</span>
                        </div>
                      </td>
                    </tr>
                  </>
) : documentsData?.items.map((doc: InvoiceDocument) => (
                  <tr key={doc.id} className="hover:bg-slate-50 cursor-pointer" onClick={() => router.push(`/documents/${doc.id}`)}>
                      <td>
                        <div className="max-w-xs truncate">
                          <p className="font-medium text-slate-900 truncate">{doc.original_filename}</p>
                          <p className="text-xs text-slate-500">{doc.mime_type} · {formatBytes(doc.file_size)}</p>
                        </div>
                      </td>
                      <td className="text-sm text-slate-600">{format(new Date(doc.created_at), 'MMM d, yyyy HH:mm')}</td>
                      <td>
                        <span className={clsx('badge', statusColors[doc.status as keyof typeof statusColors] || 'badge-gray')}>
                          {doc.status}
                        </span>
                      </td>
                      <td className="text-sm text-slate-700">
                        {doc.extracted_fields?.find(f => f.field_name === 'vendor_name')?.value || '—'}
                      </td>
                      <td className="text-sm text-slate-600">{formatBytes(doc.file_size)}</td>
                      <td className="text-center">
                        <button
                          onClick={(e) => { e.stopPropagation(); router.push(`/documents/${doc.id}`); }}
                          className="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                          aria-label={`View ${doc.original_filename}`}
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                        </button>
                      </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {documentsData && documentsData.total_pages > 1 && (
            <div className="p-4 border-t border-slate-200 flex items-center justify-between">
              <p className="text-sm text-slate-600">
                Page {page} of {documentsData.total_pages} ({documentsData.total} total)
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="btn-secondary"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setPage(p => Math.min((documentsData?.total_pages || 1), p + 1))}
                  disabled={page >= (documentsData?.total_pages || 1)}
                  className="btn-secondary"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default DocumentsPage;