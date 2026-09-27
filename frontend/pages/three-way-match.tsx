'use client';

import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTier } from '@/hooks/useQueries';
import { useAuth } from '@/contexts/AuthContext';
import { Plus, FileText, Search, Filter, ChevronDown, ChevronUp, Download, Eye, MoreHorizontal, Shield, AlertTriangle, Copy, CheckCircle, AlertCircle, Upload, ArrowRight, ArrowLeft, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { format } from 'date-fns';

export default function ThreeWayMatchPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { data: tier } = useTier();
  const [pos, setPos] = useState([]);
  const [gr, setGr] = useState([]);
  const [statusFilter, setStatusFilter] = useState<string[]>(['matched', 'mismatch', 'partial']);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sortBy, setSortBy] = useState<'date' | 'amount' | 'status'>('date');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  const enabledFeatures = tier?.features || {};
  const isEnabled = enabledFeatures.three_way_match;

  if (!isEnabled) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="card p-12 max-w-md mx-auto text-center">
          <Shield className="mx-auto w-16 h-16 text-slate-300 mb-4" />
          <h2 className="text-xl font-semibold text-slate-900 mb-2">3-Way Match Not Available</h2>
          <p className="text-slate-600 mb-6">This feature requires the Premium tier. Please upgrade your plan to access 3-Way Match functionality.</p>
        </div>
      </div>
    );
  }

  // Mock data for demonstration
  const mockMatches = [
    { id: '1', po_number: 'PO-2024-001', invoice_number: 'INV-001', po_amount: 10000, invoice_amount: 10000, gr_amount: 10000, status: 'matched', date: '2024-01-15', vendor: 'Acme Corp' },
    { id: '2', po_number: 'PO-2024-002', invoice_number: 'INV-002', po_amount: 5000, invoice_amount: 5500, gr_amount: 5000, status: 'mismatch', date: '2024-01-14', vendor: 'Beta Inc' },
    { id: '3', po_number: 'PO-2024-003', invoice_number: 'INV-003', po_amount: 25000, invoice_amount: 25000, gr_amount: 24500, status: 'partial', date: '2024-01-13', vendor: 'Gamma Ltd' },
  ];

  const handleSort = (field: 'date' | 'amount' | 'status') => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  const statusColors = {
    matched: 'badge-success',
    mismatch: 'badge-danger',
    partial: 'badge-warning',
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="top-bar">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-900">3-Way Match</h1>
          <span className="badge-primary ml-2">Premium</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-600 hidden sm:block">
            Match Purchase Orders, Invoices & Goods Receipts
          </span>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="card p-6">
            <p className="text-sm text-slate-600">Total Matches</p>
            <p className="text-3xl font-bold text-slate-900">156</p>
          </div>
          <div className="card p-6 border-l-4 border-success-500">
            <p className="text-sm text-slate-600">Matched</p>
            <p className="text-3xl font-bold text-success-600">142</p>
          </div>
          <div className="card p-6 border-l-4 border-danger-500">
            <p className="text-sm text-slate-600">Mismatches</p>
            <p className="text-3xl font-bold text-danger-600">8</p>
          </div>
          <div className="card p-6 border-l-4 border-warning-500">
            <p className="text-sm text-slate-600">Partial Matches</p>
            <p className="text-3xl font-bold text-warning-600">6</p>
          </div>
        </div>

        {/* Filters */}
        <div className="card mb-6">
          <div className="p-4 border-b border-slate-200">
            <div className="flex flex-wrap items-center gap-4">
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l4.35 4.35"/></svg>
                <input
                  type="text"
                  placeholder="Search PO, Invoice, Vendor..."
                  className="input pl-10 w-64"
                />
              </div>
              <select className="input w-auto">
                <option value="">All Status</option>
                <option value="matched">Matched</option>
                <option value="mismatch">Mismatch</option>
                <option value="partial">Partial</option>
              </select>
              <select className="input w-auto">
                <option value="">All Vendors</option>
                <option value="Acme Corp">Acme Corp</option>
                <option value="Beta Inc">Beta Inc</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>PO Number</th>
                  <th>Invoice #</th>
                  <th>Vendor</th>
                  <th>PO Amount</th>
                  <th>Invoice Amt</th>
                  <th>GR Amount</th>
                  <th>Variance</th>
                  <th>Status</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {mockMatches.map((match) => (
                  <tr key={match.id} className="hover:bg-slate-50">
                    <td className="font-mono font-medium text-slate-900">{match.po_number}</td>
                    <td className="font-mono text-slate-700">{match.invoice_number}</td>
                    <td className="text-slate-700">{match.vendor}</td>
                    <td className="text-right font-mono">${match.po_amount.toLocaleString()}</td>
                    <td className="text-right font-mono">${match.invoice_amount.toLocaleString()}</td>
                    <td className="text-right font-mono">${match.gr_amount.toLocaleString()}</td>
                    <td className="text-right font-mono text-danger-600">
                      ${(match.invoice_amount - match.po_amount).toLocaleString()}
                    </td>
                    <td>
                      <span className={`badge ${statusColors[match.status as keyof typeof statusColors]}`}>
                        {match.status.charAt(0).toUpperCase() + match.status.slice(1)}
                      </span>
                    </td>
                    <td className="text-center">
                      <button className="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors" aria-label="View details">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}