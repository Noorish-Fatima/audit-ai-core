'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useRules, useCreateRule, useUpdateRule, useDeleteRule, useTier, Rule } from '@/hooks/useQueries';
import { useAuth } from '@/contexts/AuthContext';
import { Plus, Edit, Trash2, ChevronDown, ChevronUp, Search, X, Shield, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import clsx from 'clsx';
import { format } from 'date-fns';

export default function RulesPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { data: tier } = useTier();
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState<Rule | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    condition: {},
    severity: 'medium',
  });

  const { data: rulesData, isLoading } = useRules();
  const createRuleMutation = useCreateRule();
  const updateRuleMutation = useUpdateRule();
  const deleteRuleMutation = useDeleteRule();

  const canManageRules = user?.role === 'admin';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingRule) {
        await updateRuleMutation.mutateAsync({ id: editingRule.id, ...formData });
      } else {
        await createRuleMutation.mutateAsync(formData);
      }
      setShowForm(false);
      setEditingRule(null);
      setFormData({ name: '', description: '', condition: {}, severity: 'medium' });
    } catch (err) {
      console.error('Failed to save rule:', err);
    }
  };

  const handleEdit = (rule: Rule) => {
    setEditingRule(rule);
    setFormData({
      name: rule.name,
      description: rule.description || '',
      condition: rule.condition,
      severity: rule.severity,
    });
    setShowForm(true);
  };

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this rule?')) {
      await deleteRuleMutation.mutateAsync(id);
    }
  };

  const handleConditionChange = (key: string, value: unknown) => {
    setFormData(prev => ({
      ...prev,
      condition: { ...prev.condition, [key]: value },
    }));
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="top-bar">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-900">Rules Engine</h1>
        </div>
        <div className="flex items-center gap-3">
          {canManageRules && (
            <button onClick={() => { setEditingRule(null); setFormData({ name: '', description: '', condition: {}, severity: 'medium' }); setShowForm(true); }} className="btn-primary">
              <Plus className="w-4 h-4 mr-2" />
              New Rule
            </button>
          )}
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Search */}
        <div className="mb-6">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search rules..."
              className="input pl-10 w-full"
            />
          </div>
        </div>

        {/* Rules Table */}
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="w-12"></th>
                  <th>Name</th>
                  <th>Description</th>
                  <th>Condition</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                      <div className="flex flex-col items-center gap-3">
                        <div className="w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full animate-spin" />
                        <span className="text-sm">Loading rules...</span>
                      </div>
                    </td>
                  </tr>
                ) : rulesData?.filter((r: Rule) => r.name.toLowerCase().includes(searchQuery.toLowerCase())).map((rule: Rule) => (
                  <tr key={rule.id} className="hover:bg-slate-50">
                    <td className="text-center">
                      {rule.active ? (
                        <span className="w-2.5 h-2.5 bg-success-500 rounded-full" />
                      ) : (
                        <span className="w-2.5 h-2.5 bg-slate-300 rounded-full" />
                      )}
                    </td>
                    <td className="font-medium text-slate-900">{rule.name}</td>
                    <td className="text-slate-600 text-sm max-w-xs truncate">{rule.description || '—'}</td>
                    <td className="text-sm text-slate-600 font-mono text-xs max-w-xs truncate block">
                      {JSON.stringify(rule.condition).substring(0, 100)}{JSON.stringify(rule.condition).length > 100 ? '...' : ''}
                    </td>
                    <td>
                      <span className={`badge ${['critical', 'high'].includes(rule.severity) ? 'badge-danger' : rule.severity === 'medium' ? 'badge-warning' : 'badge-gray'}`}>
                        {rule.severity}
                      </span>
                    </td>
                    <td>
                      <span className={clsx('badge', rule.active ? 'badge-success' : 'badge-gray')}>
                        {rule.active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="text-center">
                      <div className="flex items-center justify-center gap-1">
                        <button onClick={() => handleEdit(rule)} className="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors" aria-label="Edit rule"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v12a2 2 0 002 2h14a2 2 0 002-2v-1"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5a2.121 2.121 0 000-3L19.5 3.5a2.121 2.121 0 00-3 0l-9.5 9.5"/></svg></button>
                        <button onClick={() => handleDelete(rule.id)} className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 6m14 0h-4m4 0l-1.146 4H3.146l-.964 4H3m8 0v12a2 2 0 002 2h8a2 2 0 002-2V5h-4m0-4H5a1 1 0 00-1 1v12a1 1 0 001 1h12a1 1 0 001-1V3z"/></svg></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {isLoading ? null : rulesData?.filter((r: Rule) => r.name.toLowerCase().includes(searchQuery.toLowerCase())).length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center">
                      <div className="empty-state">
                        <Search className="empty-state-icon w-12 h-12" />
                        <p className="text-lg font-medium">No rules found</p>
                        <p className="text-sm">Try adjusting your search</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Rule Form Modal */}
        {showForm && (
          <div className="dialog-overlay" onClick={() => { setShowForm(false); setEditingRule(null); setFormData({ name: '', description: '', condition: {}, severity: 'medium' }); }}>
            <div className="dialog-content" onClick={e => e.stopPropagation()}>
              <div className="dialog-header">
                <h3 className="dialog-title">{editingRule ? 'Edit Rule' : 'Create New Rule'}</h3>
                <button onClick={() => { setShowForm(false); setEditingRule(null); setFormData({ name: '', description: '', condition: {}, severity: 'medium' }); }} className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
              </div>
              <form onSubmit={handleSubmit} className="dialog-body space-y-6">
                <div>
                  <label className="label">Rule Name *</label>
                  <input type="text" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} className="input" placeholder="Enter rule name" required />
                </div>
                <div>
                  <label className="label">Description</label>
                  <textarea value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} className="input" rows={3} placeholder="Describe what this rule checks" />
                </div>
                <div>
                  <label className="label">Severity *</label>
                  <select value={formData.severity} onChange={e => setFormData({...formData, severity: e.target.value})} className="input">
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
                <div>
                  <label className="label">Condition (JSON) *</label>
                  <textarea
                    value={JSON.stringify(formData.condition, null, 2)}
                    onChange={e => {
                      try {
                        setFormData({...formData, condition: JSON.parse(e.target.value)});
                      } catch {}
                    }}
                    className="input font-mono text-sm"
                    rows={8}
                    placeholder='{"field": "invoice.total_amount", "operator": "gt", "value": 10000}'
                    required
                  />
                  <p className="text-xs text-slate-500 mt-1">Enter a valid JSON condition object. See documentation for supported fields and operators.</p>
                </div>
                <div className="dialog-footer">
                  <button type="button" onClick={() => { setShowForm(false); setEditingRule(null); setFormData({ name: '', description: '', condition: {}, severity: 'medium' }); }} className="btn-secondary">Cancel</button>
                  <button type="submit" className="btn-primary" disabled={createRuleMutation.isPending || updateRuleMutation.isPending}>
                    {editingRule ? 'Update Rule' : 'Create Rule'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}