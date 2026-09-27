'use client';

import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useReviewQueue, useSubmitReview, useTier, ReviewQueueItem } from '@/hooks/useQueries';
import { useAuth } from '@/contexts/AuthContext';
import { ChevronLeft, ChevronRight, Filter, ChevronDown, ChevronUp, Search, X, Flag, AlertTriangle, Copy, CheckCircle, AlertCircle } from 'lucide-react';
import clsx from 'clsx';
import { format } from 'date-fns';

export default function ReviewQueuePage() {
  const router = useRouter();
  const { user } = useAuth();
  const { data: tier } = useTier();
  const [statusFilter, setStatusFilter] = useState<string[]>(['review', 'flagged', 'duplicate']);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sortBy, setSortBy] = useState<'priority' | 'date'>('priority');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<ReviewQueueItem | null>(null);
  const [showDetail, setShowDetail] = useState(false);

  const enabledFeatures = tier?.features || {};
  const canReview = user?.role === 'admin' || user?.role === 'approver' || user?.role === 'auditor';

  const { data: queueData, isLoading, refetch } = useReviewQueue({
    status: statusFilter.length > 0 ? statusFilter : undefined,
    page,
    pageSize,
  });

  const submitReviewMutation = useSubmitReview();

  const handleAction = async (docId: string, action: 'verify' | 'flag' | 'confirm_duplicate') => {
    await submitReviewMutation.mutateAsync({
      documentId: docId,
      decision: { action },
    });
    refetch();
  };

  const openDocument = (doc: ReviewQueueItem) => {
    setSelectedDoc(doc);
    setShowDetail(true);
  };

  const closeDetail = () => {
    setSelectedDoc(null);
    setShowDetail(false);
  };

  const handleSort = (field: 'priority' | 'date') => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  const statusOptions = [
    { value: 'review', label: 'Review' },
    { value: 'flagged', label: 'Flagged' },
    { value: 'duplicate', label: 'Duplicate' },
  ];

  const severityColors = {
    critical: 'badge-danger',
    high: 'badge-danger',
    medium: 'badge-warning',
    low: 'badge-gray',
  };

  const getPriorityLabel = (score: number) => {
    if (score >= 80) return { label: 'Critical', className: 'badge-danger' };
    if (score >= 60) return { label: 'High', className: 'badge-danger' };
    if (score >= 40) return { label: 'Medium', className: 'badge-warning' };
    if (score >= 20) return { label: 'Low', className: 'badge-warning' };
    return { label: 'Minimal', className: 'badge-gray' };
  };

  const statusColors = {
    review: 'badge-warning',
    flagged: 'badge-danger',
    duplicate: 'badge-danger',
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="top-bar">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-900">Review Queue</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-600 hidden sm:block">
            Showing documents requiring review
          </span>
        </div>
      </header>

      <div className="flex">
        {/* Filters Sidebar */}
        <aside className={clsx('w-72 bg-white border-r border-slate-200 flex flex-col h-[calc(100vh-64px)] overflow-y-auto lg:block hidden', 'border-r border-slate-200')}>
          <div className="p-4 border-b border-slate-200">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-900">Filters</h3>
              <button onClick={() => setShowFilters(!showFilters)} className="btn-ghost text-sm">
                {showFilters ? <ChevronUp className="w-4 h-4 mr-1" /> : <ChevronDown className="w-4 h-4 mr-1" />}
                {showFilters ? 'Hide' : 'Show'} Filters
              </button>
            </div>
          </div>

          <div className={clsx('p-4', showFilters ? 'block' : 'hidden')}>
            {/* Search */}
            <div className="mb-4">
              <label className="label">Search</label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search filename, vendor..."
                  className="input pl-10"
                />
                {searchQuery && (
                  <button onClick={() => setSearchQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                    <X className="w-4 h-4" />
                  </button>
                )}
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

            {/* Sort */}
            <div className="mb-4">
              <label className="label">Sort By</label>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'priority' | 'date')}
                className="input"
              >
                <option value="priority">Priority</option>
                <option value="date">Date</option>
              </select>
            </div>

            <div className="mb-4">
              <label className="label">Order</label>
              <select
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
                className="input"
              >
                <option value="desc">Descending</option>
                <option value="asc">Ascending</option>
              </select>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 overflow-auto">
          {/* Toolbar */}
          <div className="toolbar">
            <div className="toolbar-group">
              <h2 className="text-lg font-semibold text-slate-900">Review Queue</h2>
              <span className="px-2 py-0.5 bg-slate-100 text-slate-600 text-sm rounded">
                {queueData?.total || 0} documents
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
                  <th className="w-12"></th>
                  <th onClick={() => handleSort('priority')} className="cursor-pointer select-none">
                    <div className="flex items-center gap-1">
                      Priority
                      {sortBy === 'priority' && (sortOrder === 'asc' ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />)}
                    </div>
                  </th>
                  <th onClick={() => handleSort('date')} className="cursor-pointer select-none">
                    <div className="flex items-center gap-1">
                      Date
                      {sortBy === 'date' && (sortOrder === 'asc' ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />)}
                    </div>
                  </th>
                  <th>Document</th>
                  <th>Vendor</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                      <div className="flex flex-col items-center gap-3">
                        <div className="w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full animate-spin" />
                        <span className="text-sm">Loading review queue...</span>
                      </div>
                    </td>
                  </tr>
                ) : queueData?.items.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center">
                      <div className="empty-state">
                        <Search className="empty-state-icon w-12 h-12" />
                        <p className="text-lg font-medium">No documents found</p>
                        <p className="text-sm">Try adjusting your filters</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  queueData?.items.map((doc: ReviewQueueItem) => (
                    <tr key={doc.id} className="hover:bg-slate-50 cursor-pointer" onClick={() => openDocument(doc)}>
                      <td className="text-center">
                        <span className={clsx('badge', getPriorityLabel(doc.priority_score).className)}>
                          {getPriorityLabel(doc.priority_score).label}
                        </span>
                      </td>
                      <td className="text-sm text-slate-600">
                        {format(new Date(doc.created_at), 'MMM d, yyyy HH:mm')}
                      </td>
                      <td>
                        <div className="max-w-xs truncate">
                          <p className="font-medium text-slate-900 truncate">{doc.original_filename}</p>
                          <p className="text-xs text-slate-500">{doc.mime_type} · {formatBytes(doc.file_size)}</p>
                        </div>
                      </td>
                      <td className="text-sm text-slate-700 truncate max-w-xs">
                        {doc.fraud_flag_types?.length > 0 ? (
                          <span className="text-primary-600 font-medium">{doc.fraud_flag_types.join(', ')}</span>
                        ) : (
                          <span className="text-slate-500">No flags</span>
                        )}
                      </td>
                      <td className="text-sm text-slate-700 text-right font-medium">
                        ${doc.file_size ? '' : ''} {/* Amount would come from extracted fields */}
                      </td>
                      <td>
                        <span className={clsx('badge', statusColors[doc.status as keyof typeof statusColors] || 'badge-gray')}>
                          {doc.status}
                        </span>
                      </td>
                      <td className="text-center">
                        <button
                          onClick={(e) => { e.stopPropagation(); openDocument(doc); }}
                          className="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                          aria-label={`View ${doc.original_filename}`}
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {queueData && queueData.total_pages > 1 && (
            <div className="p-4 border-t border-slate-200 flex items-center justify-between">
              <p className="text-sm text-slate-600">
                Page {page} of {queueData.total_pages} ({queueData.total} total)
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
                  onClick={() => setPage(p => Math.min(queueData.total_pages, p + 1))}
                  disabled={page >= queueData.total_pages}
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

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}