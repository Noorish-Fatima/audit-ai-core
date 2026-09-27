'use client';

import React, { useState } from 'react';
import { useReportSummary } from '@/hooks/useQueries';
import { FeatureGate } from '@/components/FeatureGate';
import { BarChart3 } from 'lucide-react';

function BarRow({ label, value, max, suffix = '' }: { label: string; value: number; max: number; suffix?: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="w-40 shrink-0 text-sm text-slate-700 truncate" title={label}>{label}</span>
      <div className="flex-1 h-5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-primary-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-24 shrink-0 text-right text-sm font-medium text-slate-900 font-mono">
        {value.toLocaleString()}{suffix}
      </span>
    </div>
  );
}

function MoneyBarRow({ label, spend, maxSpend }: { label: string; spend: number; maxSpend: number }) {
  const pct = maxSpend > 0 ? Math.round((spend / maxSpend) * 100) : 0;
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="w-40 shrink-0 text-sm text-slate-700 truncate" title={label}>{label}</span>
      <div className="flex-1 h-5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-success-600 rounded-full transition-all" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-28 shrink-0 text-right text-sm font-medium text-slate-900 font-mono">
        ${spend.toLocaleString(undefined, { maximumFractionDigits: 2 })}
      </span>
    </div>
  );
}

function ReportsPageInner() {
  const [days, setDays] = useState(90);
  const { data, isLoading, error } = useReportSummary(days);

  const statusEntries = Object.entries(data?.aging.by_status || {}).sort((a, b) => b[1] - a[1]);
  const statusMax = Math.max(1, ...statusEntries.map(([, v]) => v));
  const bucketOrder = ['0-7 days', '8-30 days', '31-90 days', '90+ days'];
  const bucketEntries = bucketOrder
    .filter((b) => data?.aging.by_age_bucket?.[b] !== undefined)
    .map((b) => [b, data!.aging.by_age_bucket[b]] as [string, number]);
  const bucketMax = Math.max(1, ...bucketEntries.map(([, v]) => v));
  const vendors = data?.top_vendors || [];
  const maxSpend = Math.max(1, ...vendors.map((v) => Number(v.total_spend) || 0));

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="top-bar">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-primary-600" />
            Reports
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-slate-600" htmlFor="window">Window</label>
          <select
            id="window"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="input w-auto"
          >
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {isLoading ? (
          <div className="card p-12 flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm text-slate-500">Loading report...</span>
          </div>
        ) : error || !data ? (
          <div className="card p-12 text-center">
            <p className="text-lg font-medium text-slate-900">Could not load report</p>
            <p className="text-sm text-slate-500 mt-1">Please try again later.</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="card p-6">
                <p className="text-sm text-slate-500">Total documents</p>
                <p className="text-3xl font-bold text-slate-900 mt-1">{data.aging.total.toLocaleString()}</p>
              </div>
              <div className="card p-6">
                <p className="text-sm text-slate-500">Vendors tracked</p>
                <p className="text-3xl font-bold text-slate-900 mt-1">{vendors.length.toLocaleString()}</p>
              </div>
              <div className="card p-6">
                <p className="text-sm text-slate-500">Window</p>
                <p className="text-3xl font-bold text-slate-900 mt-1">{data.window_days} days</p>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="card p-6">
                <h3 className="font-semibold text-slate-900 mb-1">Documents by status</h3>
                <p className="text-xs text-slate-500 mb-3">Aging across all documents in the system</p>
                {statusEntries.length === 0 ? (
                  <p className="text-sm text-slate-500">No documents yet.</p>
                ) : (
                  statusEntries.map(([status, count]) => (
                    <BarRow key={status} label={status.replace(/_/g, ' ')} value={count} max={statusMax} />
                  ))
                )}
              </div>

              <div className="card p-6">
                <h3 className="font-semibold text-slate-900 mb-1">Documents by age</h3>
                <p className="text-xs text-slate-500 mb-3">Days since upload</p>
                {bucketEntries.map(([bucket, count]) => (
                  <BarRow key={bucket} label={bucket} value={count} max={bucketMax} />
                ))}
              </div>
            </div>

            <div className="card p-6">
              <h3 className="font-semibold text-slate-900 mb-1">Top vendors by spend</h3>
              <p className="text-xs text-slate-500 mb-3">Same spend computation as Ask AI uses</p>
              {vendors.length === 0 ? (
                <p className="text-sm text-slate-500">No vendor spend in this window.</p>
              ) : (
                vendors.map((v) => (
                  <MoneyBarRow key={v.vendor} label={v.vendor} spend={Number(v.total_spend) || 0} maxSpend={maxSpend} />
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function ReportsPage() {
  return (
    <FeatureGate feature="reporting">
      <ReportsPageInner />
    </FeatureGate>
  );
}
