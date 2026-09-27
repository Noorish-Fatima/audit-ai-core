'use client';

import React, { useState } from 'react';
import { useRules, useCreateRule, useUpdateRule, useDeleteRule, Rule } from '@/hooks/useQueries';
import { useAuth } from '@/contexts/AuthContext';
import { FeatureGate } from '@/components/FeatureGate';
import { Plus, Search, X } from 'lucide-react';
import clsx from 'clsx';

const FIELD_OPTIONS = [
  { value: 'invoice.invoice_number', label: 'Invoice number' },
  { value: 'invoice.vendor_name', label: 'Vendor name' },
  { value: 'invoice.total_amount', label: 'Invoice amount' },
  { value: 'invoice.invoice_date', label: 'Invoice date' },
  { value: 'invoice.tax_amount', label: 'Tax amount' },
  { value: 'invoice.currency', label: 'Currency' },
  { value: 'vendor.canonical_name', label: 'Vendor (canonical)' },
  { value: 'vendor.is_approved', label: 'Vendor is approved' },
  { value: 'vendor.is_new', label: 'Vendor is new' },
];

const OPERATOR_OPTIONS = [
  { value: 'equals', label: 'is equal to' },
  { value: 'not_equals', label: 'is not equal to' },
  { value: 'contains', label: 'contains' },
  { value: 'gt', label: 'is greater than' },
  { value: 'gte', label: 'is greater than or equal to' },
  { value: 'lt', label: 'is less than' },
  { value: 'lte', label: 'is less than or equal to' },
];

const NUMERIC_OPERATORS = new Set(['gt', 'gte', 'lt', 'lte']);

interface LeafCondition {
  kind: 'leaf';
  field: string;
  operator: string;
  value: string;
}

interface GroupCondition {
  kind: 'group';
  logic: 'and' | 'or';
  conditions: LeafCondition[];
}

type BuilderItem = LeafCondition | GroupCondition;

const emptyLeaf = (): LeafCondition => ({
  kind: 'leaf',
  field: 'invoice.total_amount',
  operator: 'gt',
  value: '',
});

const fieldLabel = (field: string): string =>
  FIELD_OPTIONS.find((f) => f.value === field)?.label || field.replace(/_/g, ' ');

const operatorPhrase = (operator: string): string =>
  OPERATOR_OPTIONS.find((o) => o.value === operator)?.label || operator;

const formatValue = (field: string, value: string): string => {
  if (field === 'invoice.total_amount' || field === 'invoice.tax_amount') {
    const num = Number(value);
    if (!Number.isNaN(num)) {
      return '$' + num.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
  }
  if (value === 'true') return 'true';
  if (value === 'false') return 'false';
  return value === '' ? '(empty)' : `"${value}"`;
};

function describeLeaf(leaf: LeafCondition): string {
  return `${fieldLabel(leaf.field)} ${operatorPhrase(leaf.operator)} ${formatValue(leaf.field, leaf.value)}`;
}

function describeItems(logic: 'and' | 'or', parts: string[]): string {
  if (parts.length === 0) return '(no conditions yet)';
  if (parts.length === 1) return parts[0];
  return parts.join(logic === 'and' ? ' AND ' : ' OR ');
}

export function describeRule(logic: 'and' | 'or', items: BuilderItem[]): string {
  if (items.length === 0) return 'Flag if (no conditions yet)';
  const parts = items.map((item) =>
    item.kind === 'leaf' ? describeLeaf(item) : `(${describeItems(item.logic, item.conditions.map(describeLeaf))})`
  );
  return `Flag if ${describeItems(logic, parts)}`;
}

function coerceValue(operator: string, value: string): string | number | boolean {
  const trimmed = value.trim();
  if (NUMERIC_OPERATORS.has(operator)) {
    const num = Number(trimmed);
    return Number.isNaN(num) ? trimmed : num;
  }
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  return value;
}

function buildConditionJSON(logic: 'and' | 'or', items: BuilderItem[]): Record<string, unknown> {
  const convert = (list: LeafCondition[]) =>
    list.map((c) => ({ field: c.field, operator: c.operator, value: coerceValue(c.operator, c.value) }));
  const parts: unknown[] = items.map((item) =>
    item.kind === 'leaf'
      ? { field: item.field, operator: item.operator, value: coerceValue(item.operator, item.value) }
      : { [item.logic]: convert(item.conditions) }
  );
  if (parts.length === 1 && items[0].kind === 'leaf') {
    return parts[0] as Record<string, unknown>;
  }
  return { [logic]: parts };
}

function parseConditionJSON(condition: unknown): { logic: 'and' | 'or'; items: BuilderItem[] } {
  const toLeaf = (c: unknown): LeafCondition => {
    const obj = (c || {}) as Record<string, unknown>;
    return {
      kind: 'leaf',
      field: typeof obj.field === 'string' ? obj.field : 'invoice.total_amount',
      operator: typeof obj.operator === 'string' ? obj.operator : 'equals',
      value: obj.value === undefined || obj.value === null ? '' : String(obj.value),
    };
  };
  if (condition && typeof condition === 'object') {
    const obj = condition as Record<string, unknown>;
    for (const logic of ['and', 'or'] as const) {
      const list = obj[logic];
      if (Array.isArray(list)) {
        const items: BuilderItem[] = list.map((entry) => {
          if (entry && typeof entry === 'object') {
            const e = entry as Record<string, unknown>;
            if (Array.isArray(e.and)) {
              return { kind: 'group', logic: 'and', conditions: (e.and as unknown[]).map(toLeaf) } as GroupCondition;
            }
            if (Array.isArray(e.or)) {
              return { kind: 'group', logic: 'or', conditions: (e.or as unknown[]).map(toLeaf) } as GroupCondition;
            }
          }
          return toLeaf(entry);
        });
        return { logic, items };
      }
    }
    // Single leaf triplet
    if (typeof obj.field === 'string') {
      return { logic: 'and', items: [toLeaf(obj)] };
    }
  }
  return { logic: 'and', items: [emptyLeaf()] };
}

const blankForm = () => ({
  name: '',
  description: '',
  severity: 'medium',
  topLogic: 'and' as 'and' | 'or',
  items: [emptyLeaf()] as BuilderItem[],
});

function RulesPageInner() {
  const { user } = useAuth();
  const [editingRule, setEditingRule] = useState<Rule | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState(blankForm());

  const { data: rulesData, isLoading } = useRules();
  const createRuleMutation = useCreateRule();
  const updateRuleMutation = useUpdateRule();
  const deleteRuleMutation = useDeleteRule();

  const canManageRules = user?.role === 'admin';

  const openCreate = () => {
    setEditingRule(null);
    setFormData(blankForm());
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingRule(null);
    setFormData(blankForm());
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const condition = buildConditionJSON(formData.topLogic, formData.items);
    const payload = {
      name: formData.name,
      description: formData.description || undefined,
      condition,
      severity: formData.severity,
    };
    try {
      if (editingRule) {
        await updateRuleMutation.mutateAsync({ id: editingRule.id, ...payload });
      } else {
        await createRuleMutation.mutateAsync(payload);
      }
      closeForm();
    } catch (err) {
      console.error('Failed to save rule:', err);
    }
  };

  const handleEdit = (rule: Rule) => {
    setEditingRule(rule);
    const parsed = parseConditionJSON(rule.condition);
    setFormData({
      name: rule.name,
      description: rule.description || '',
      severity: rule.severity,
      topLogic: parsed.logic,
      items: parsed.items.length > 0 ? parsed.items : [emptyLeaf()],
    });
    setShowForm(true);
  };

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this rule?')) {
      await deleteRuleMutation.mutateAsync(id);
    }
  };

  const handleToggleActive = async (rule: Rule) => {
    await updateRuleMutation.mutateAsync({ id: rule.id, active: !rule.active });
  };

  const updateLeaf = (index: number, patch: Partial<LeafCondition>) => {
    setFormData((prev) => {
      const items = [...prev.items];
      const item = items[index];
      if (item.kind !== 'leaf') return prev;
      items[index] = { ...item, ...patch };
      return { ...prev, items };
    });
  };

  const updateGroupLeaf = (groupIndex: number, leafIndex: number, patch: Partial<LeafCondition>) => {
    setFormData((prev) => {
      const items = [...prev.items];
      const group = items[groupIndex];
      if (group.kind !== 'group') return prev;
      const conditions = [...group.conditions];
      conditions[leafIndex] = { ...conditions[leafIndex], ...patch };
      items[groupIndex] = { ...group, conditions };
      return { ...prev, items };
    });
  };

  const removeItem = (index: number) => {
    setFormData((prev) => ({ ...prev, items: prev.items.filter((_, i) => i !== index) }));
  };

  const preview = describeRule(formData.topLogic, formData.items);
  const filtered = (rulesData || []).filter((r: Rule) =>
    r.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="top-bar">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-900">Rules Engine</h1>
        </div>
        <div className="flex items-center gap-3">
          {canManageRules && (
            <button onClick={openCreate} className="btn-primary">
              <Plus className="w-4 h-4 mr-2" />
              New Rule
            </button>
          )}
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
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
                ) : (
                  filtered.map((rule: Rule) => (
                    <tr key={rule.id} className="hover:bg-slate-50">
                      <td className="text-center">
                        {rule.active ? (
                          <span className="w-2.5 h-2.5 bg-success-500 rounded-full inline-block" />
                        ) : (
                          <span className="w-2.5 h-2.5 bg-slate-300 rounded-full inline-block" />
                        )}
                      </td>
                      <td className="font-medium text-slate-900">{rule.name}</td>
                      <td className="text-slate-600 text-sm max-w-xs truncate">{rule.description || '—'}</td>
                      <td className="text-sm text-slate-600 text-xs max-w-xs truncate">
                        {(() => {
                          const parsed = parseConditionJSON(rule.condition);
                          return describeRule(parsed.logic, parsed.items);
                        })()}
                      </td>
                      <td>
                        <span className={`badge ${['critical', 'high'].includes(rule.severity) ? 'badge-danger' : rule.severity === 'medium' ? 'badge-warning' : 'badge-gray'}`}>
                          {rule.severity}
                        </span>
                      </td>
                      <td>
                        <button
                          onClick={() => handleToggleActive(rule)}
                          disabled={!canManageRules || updateRuleMutation.isPending}
                          className={clsx('badge', rule.active ? 'badge-success' : 'badge-gray')}
                          title={canManageRules ? (rule.active ? 'Deactivate rule' : 'Activate rule') : undefined}
                        >
                          {rule.active ? 'Active' : 'Inactive'}
                        </button>
                      </td>
                      <td className="text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button onClick={() => handleEdit(rule)} disabled={!canManageRules} className="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors" aria-label="Edit rule">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v12a2 2 0 002 2h14a2 2 0 002-2v-1" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                          </button>
                          <button onClick={() => handleDelete(rule.id)} disabled={!canManageRules} className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" aria-label="Delete rule">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
                {!isLoading && filtered.length === 0 && (
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

        {showForm && (
          <div className="dialog-overlay" onClick={closeForm}>
            <div className="dialog-content" onClick={(e) => e.stopPropagation()}>
              <div className="dialog-header">
                <h3 className="dialog-title">{editingRule ? 'Edit Rule' : 'Create New Rule'}</h3>
                <button onClick={closeForm} className="p-1 text-slate-400 hover:text-slate-600" aria-label="Close">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <form onSubmit={handleSubmit} className="dialog-body space-y-6">
                <div>
                  <label className="label">Rule Name *</label>
                  <input type="text" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} className="input" placeholder="Enter rule name" required />
                </div>
                <div>
                  <label className="label">Description</label>
                  <textarea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} className="input" rows={2} placeholder="Describe what this rule checks" />
                </div>
                <div>
                  <label className="label">Severity *</label>
                  <select value={formData.severity} onChange={(e) => setFormData({ ...formData, severity: e.target.value })} className="input">
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="label mb-0">Conditions *</label>
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-slate-500">Match</span>
                      <select
                        value={formData.topLogic}
                        onChange={(e) => setFormData({ ...formData, topLogic: e.target.value as 'and' | 'or' })}
                        className="input w-auto py-1"
                        aria-label="Top-level logic"
                      >
                        <option value="and">ALL (AND)</option>
                        <option value="or">ANY (OR)</option>
                      </select>
                    </div>
                  </div>

                  <div className="space-y-3">
                    {formData.items.map((item, index) => (
                      <div key={index}>
                        {index > 0 && (
                          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider my-1">
                            {formData.topLogic === 'and' ? 'AND' : 'OR'}
                          </p>
                        )}
                        {item.kind === 'leaf' ? (
                          <div className="flex flex-wrap items-center gap-2 p-3 bg-slate-50 border border-slate-200 rounded-lg">
                            <select value={item.field} onChange={(e) => updateLeaf(index, { field: e.target.value })} className="input w-auto flex-1 min-w-[140px]" aria-label="Field">
                              {FIELD_OPTIONS.map((f) => (
                                <option key={f.value} value={f.value}>{f.label}</option>
                              ))}
                            </select>
                            <select value={item.operator} onChange={(e) => updateLeaf(index, { operator: e.target.value })} className="input w-auto flex-1 min-w-[140px]" aria-label="Operator">
                              {OPERATOR_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                              ))}
                            </select>
                            <input
                              type="text"
                              value={item.value}
                              onChange={(e) => updateLeaf(index, { value: e.target.value })}
                              className="input flex-1 min-w-[100px]"
                              placeholder="Value"
                              aria-label="Value"
                            />
                            <button type="button" onClick={() => removeItem(index)} disabled={formData.items.length <= 1} className="p-1.5 text-slate-400 hover:text-red-600 disabled:opacity-30" aria-label="Remove condition">
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        ) : (
                          <div className="p-3 bg-primary-50/50 border border-primary-200 rounded-lg space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-semibold text-primary-700 uppercase tracking-wider">
                                Nested group — match {item.logic === 'and' ? 'ALL' : 'ANY'}
                              </span>
                              <div className="flex items-center gap-2">
                                <select
                                  value={item.logic}
                                  onChange={(e) => {
                                    const logic = e.target.value as 'and' | 'or';
                                    setFormData((prev) => {
                                      const items = [...prev.items];
                                      const g = items[index];
                                      if (g.kind !== 'group') return prev;
                                      items[index] = { ...g, logic };
                                      return { ...prev, items };
                                    });
                                  }}
                                  className="input w-auto py-1 text-xs"
                                  aria-label="Nested group logic"
                                >
                                  <option value="and">ALL (AND)</option>
                                  <option value="or">ANY (OR)</option>
                                </select>
                                <button type="button" onClick={() => removeItem(index)} className="p-1.5 text-slate-400 hover:text-red-600" aria-label="Remove group">
                                  <X className="w-4 h-4" />
                                </button>
                              </div>
                            </div>
                            {item.conditions.map((leaf, leafIndex) => (
                              <div key={leafIndex} className="flex flex-wrap items-center gap-2 p-2 bg-white border border-slate-200 rounded-lg">
                                <select value={leaf.field} onChange={(e) => updateGroupLeaf(index, leafIndex, { field: e.target.value })} className="input w-auto flex-1 min-w-[130px]" aria-label="Field">
                                  {FIELD_OPTIONS.map((f) => (
                                    <option key={f.value} value={f.value}>{f.label}</option>
                                  ))}
                                </select>
                                <select value={leaf.operator} onChange={(e) => updateGroupLeaf(index, leafIndex, { operator: e.target.value })} className="input w-auto flex-1 min-w-[130px]" aria-label="Operator">
                                  {OPERATOR_OPTIONS.map((o) => (
                                    <option key={o.value} value={o.value}>{o.label}</option>
                                  ))}
                                </select>
                                <input type="text" value={leaf.value} onChange={(e) => updateGroupLeaf(index, leafIndex, { value: e.target.value })} className="input flex-1 min-w-[90px]" placeholder="Value" aria-label="Value" />
                                <button
                                  type="button"
                                  onClick={() => {
                                    setFormData((prev) => {
                                      const items = [...prev.items];
                                      const g = items[index];
                                      if (g.kind !== 'group') return prev;
                                      items[index] = { ...g, conditions: g.conditions.filter((_, i) => i !== leafIndex) };
                                      return { ...prev, items };
                                    });
                                  }}
                                  disabled={item.conditions.length <= 1}
                                  className="p-1.5 text-slate-400 hover:text-red-600 disabled:opacity-30"
                                  aria-label="Remove nested condition"
                                >
                                  <X className="w-4 h-4" />
                                </button>
                              </div>
                            ))}
                            <button
                              type="button"
                              onClick={() => {
                                setFormData((prev) => {
                                  const items = [...prev.items];
                                  const g = items[index];
                                  if (g.kind !== 'group') return prev;
                                  items[index] = { ...g, conditions: [...g.conditions, emptyLeaf()] };
                                  return { ...prev, items };
                                });
                              }}
                              className="text-xs text-primary-600 hover:text-primary-700 font-medium"
                            >
                              + Add condition to group
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  <div className="flex gap-3 mt-3">
                    <button
                      type="button"
                      onClick={() => setFormData((prev) => ({ ...prev, items: [...prev.items, emptyLeaf()] }))}
                      className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                    >
                      + Add condition
                    </button>
                    <button
                      type="button"
                      onClick={() => setFormData((prev) => ({ ...prev, items: [...prev.items, { kind: 'group', logic: 'or', conditions: [emptyLeaf()] }] }))}
                      className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                    >
                      + Add nested AND/OR group
                    </button>
                  </div>
                </div>

                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Preview</p>
                  <p className="text-sm text-slate-900 font-medium">{preview}</p>
                  <details className="mt-2">
                    <summary className="text-xs text-slate-500 cursor-pointer">View generated JSON</summary>
                    <pre className="mt-1 p-2 bg-white border border-slate-200 rounded text-xs overflow-x-auto text-slate-700">
                      {JSON.stringify(buildConditionJSON(formData.topLogic, formData.items), null, 2)}
                    </pre>
                  </details>
                </div>

                <div className="dialog-footer">
                  <button type="button" onClick={closeForm} className="btn-secondary">Cancel</button>
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

export default function RulesPage() {
  return (
    <FeatureGate feature="rules_engine">
      <RulesPageInner />
    </FeatureGate>
  );
}
