'use client';

import React, { useState, useCallback } from 'react';
import { useRouter } from 'next/router';
import { useDocument, useDocumentFile, useSubmitReview, useReviewDocument, useTier, ExtractedField, FraudFlag, DuplicateFlag, RuleViolation } from '@/hooks/useQueries';
import { useAuth } from '@/contexts/AuthContext';
import { Download, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Edit, Save, X, CheckCircle, AlertCircle, FileText, Image, ZoomIn, ZoomOut, RotateCcw, RotateCw, MoreHorizontal, Flag, AlertTriangle, Copy, Eye, EyeOff } from 'lucide-react';
import clsx from 'clsx';
import { format } from 'date-fns';

export default function DocumentDetailPage() {
  const router = useRouter();
  const id = typeof router.query.id === 'string' ? router.query.id : '';
  const { user } = useAuth();
  const { data: tier } = useTier();
  const { data: document, isLoading, error } = useDocument(id, true);
  const submitReviewMutation = useSubmitReview();
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [showFields, setShowFields] = useState(true);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const reviewMutation = useSubmitReview();
  const { data: reviewDoc } = useReviewDocument(id, true);
  const totalPages = reviewDoc?.total_pages || 1;
  const canReview = user?.role === 'admin' || user?.role === 'approver' || user?.role === 'auditor';

  const goBack = () => router.back();
  const goPrevPage = () => setCurrentPage(p => Math.max(1, p - 1));
  const goNextPage = () => setCurrentPage(p => Math.min(totalPages, p + 1));
  const zoomIn = () => setZoom(z => Math.min(z * 1.2, 3));
  const zoomOut = () => setZoom(z => Math.max(z / 1.2, 0.5));
  const rotateLeft = () => setRotation(r => (r - 90) % 360);
  const rotateRight = () => setRotation(r => (r + 90) % 360);
  const resetView = () => { setZoom(1); setRotation(0); };

  const startEditing = (field: ExtractedField) => {
    setEditingField(field.field_name);
    setEditValue(field.value);
  };

const saveEdit = async (fieldName: string) => {
    await submitReviewMutation.mutateAsync({
      documentId: id,
      decision: {
        action: 'verify',
        corrections: [{ field_name: fieldName, corrected_value: editValue }],
      }
    });
    setEditingField(null);
  };

  const handleAction = async (action: 'verify' | 'flag' | 'confirm_duplicate') => {
    await submitReviewMutation.mutateAsync({
      documentId: id,
      decision: { action },
    });
    router.reload();
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="card p-8 text-center">
          <div className="mx-auto w-12 h-12 border-4 border-primary-600 border-t-transparent rounded-full animate-spin mb-4" />
          <p className="text-slate-600">Loading document...</p>
        </div>
      </div>
    );
  }

  if (error || !document) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="card p-8 max-w-md mx-auto">
          <div className="text-center">
            <svg className="mx-auto w-16 h-16 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M6 18L18 6M6 6l12 12"/></svg>
            <h2 className="text-xl font-semibold text-slate-900 mt-4">Document Not Found</h2>
            <p className="text-slate-600 mt-2">The document you&apos;re looking for doesn&apos;t exist or has been removed.</p>
            <button onClick={() => router.push('/documents')} className="btn-primary mt-6">Back to Documents</button>
          </div>
        </div>
      </div>
    );
  }

  const isImage = document.mime_type?.startsWith('image/');
  const isPDF = document.mime_type === 'application/pdf';
  const fileUrl = document.storage_path;

  const enabledFeatures = tier?.features || {};

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Top Bar */}
      <header className="top-bar">
        <div className="flex items-center gap-4">
          <button onClick={goBack} className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors" aria-label="Back">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <h1 className="text-lg font-semibold text-slate-900 truncate flex-1">{document.original_filename}</h1>
          <div className="flex items-center gap-2">
            <span className={`status-badge status-${document.status}`}>{document.status}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {canReview && document.status === 'review' && (
            <>
              <button onClick={() => handleAction('verify')} className="btn-success" disabled={reviewMutation.isPending}>
                <CheckCircle className="w-4 h-4 mr-2" /> Approve
              </button>
              <button onClick={() => handleAction('flag')} className="btn-danger" disabled={reviewMutation.isPending}>
                <Flag className="w-4 h-4 mr-2" /> Flag
              </button>
              <button onClick={() => handleAction('confirm_duplicate')} className="btn-secondary" disabled={reviewMutation.isPending}>
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2H10"/><path d="M16 8V6a2 2 0 00-2-2H6a2 2 0 00-2 2v8a2 2 0 002 2h8"/></svg>
                <span>Dup</span>
              </button>
            </>
          )}
          <div className="relative user-menu">
            <button className="p-2 rounded-lg text-slate-500 hover:bg-slate-100" aria-label="User menu">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 21v-3m0-9v-2"/></svg>
            </button>
          </div>
        </div>
      </header>

      <div className="split-view">
        {/* Left Pane - Document Viewer */}
        <div className="split-pane bg-slate-100">
          <div className="toolbar">
            <div className="toolbar-group">
              <button onClick={goPrevPage} disabled={currentPage <= 1} className="btn-ghost" title="Previous page" aria-label="Previous page"><ChevronLeft className="w-5 h-5" /></button>
              <span className="px-3 text-sm text-slate-700">Page {currentPage} / {totalPages}</span>
              <button onClick={goNextPage} disabled={currentPage >= totalPages} className="btn-ghost" title="Next page" aria-label="Next page"><ChevronRight className="w-5 h-5" /></button>
            </div>
            <div className="toolbar-group">
              <button onClick={zoomOut} className="btn-ghost" title="Zoom out" aria-label="Zoom out"><ZoomOut className="w-5 h-5" /></button>
              <span className="px-3 text-sm text-slate-700">{Math.round(zoom * 100)}%</span>
              <button onClick={zoomIn} className="btn-ghost" title="Zoom in" aria-label="Zoom in"><ZoomIn className="w-5 h-5" /></button>
              <button onClick={resetView} className="btn-ghost" title="Reset view" aria-label="Reset view"><RotateCcw className="w-5 h-5" /></button>
              <button onClick={rotateLeft} className="btn-ghost" title="Rotate left" aria-label="Rotate left"><RotateCcw className="w-5 h-5" /></button>
              <button onClick={rotateRight} className="btn-ghost" title="Rotate right" aria-label="Rotate right"><RotateCw className="w-5 h-5" /></button>
            </div>
            <div className="toolbar-group ml-auto">
              <button className="btn-ghost" title="Download" aria-label="Download" onClick={() => window.open(fileUrl, '_blank')}>
                <Download className="w-5 h-5" />
              </button>
            </div>
          </div>

          <div className="flex-1 flex items-center justify-center p-4 relative overflow-auto">
            {isImage && (
              <img
                src={fileUrl}
                alt={document.original_filename}
                className="max-w-full max-h-full"
                style={{ transform: `scale(${zoom}) rotate(${rotation}deg)` }}
              />
            )}
            {isPDF && (
              <iframe
                src={`${fileUrl}#page=${currentPage}&zoom=${Math.round(zoom * 100)}`}
                className="w-full h-full border-0"
                title={document.original_filename}
              />
            )}
            {!isImage && !isPDF && (
              <div className="flex flex-col items-center justify-center text-slate-500">
                <FileText className="w-16 h-16 mb-4 text-slate-300" />
                <p className="text-lg font-medium">Preview not available</p>
                <p className="text-sm">Click Download to view the document</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Pane - Extracted Fields & Flags */}
        <div className="split-pane bg-white border-l border-slate-200 flex flex-col">
          <div className="toolbar border-b border-slate-200">
            <div className="flex items-center gap-3">
              <h3 className="font-semibold text-slate-900">Extracted Fields</h3>
              <button onClick={() => setShowFields(!showFields)} className="btn-ghost text-sm">
                {showFields ? <ChevronUp className="w-4 h-4 mr-1" /> : <ChevronDown className="w-4 h-4 mr-1" />}
                {showFields ? 'Hide' : 'Show'} Fields
              </button>
            </div>
            <div className="flex items-center gap-2">
              {reviewDoc?.fraud_flags && reviewDoc.fraud_flags.length > 0 && (
                <span className="badge-danger">{reviewDoc.fraud_flags.length} Fraud Flags</span>
              )}
              {reviewDoc?.rule_violations && reviewDoc.rule_violations.length > 0 && (
                <span className="badge-danger">{reviewDoc.rule_violations.length} Rule Violations</span>
              )}
              {reviewDoc?.duplicate_flags && reviewDoc.duplicate_flags.length > 0 && (
                <span className="badge-warning">{reviewDoc.duplicate_flags.length} Duplicates</span>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-auto">
            {showFields && (
              <div className="p-4 space-y-4">
                {document.extracted_fields.map((field: ExtractedField) => {
                  const isEditing = editingField === field.field_name;
                  return (
                    <div key={field.id} className={clsx('field-row', field.is_corrected && 'field-corrected')}>
                      <div className="md:col-span-1">
                        <label className="field-label">{field.field_name.replace(/_/g, ' ')}</label>
                        {isEditing ? (
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              className="input flex-1"
                              autoFocus
                              onBlur={() => saveEdit(field.field_name)}
                              onKeyDown={(e) => e.key === 'Enter' && saveEdit(field.field_name)}
                            />
                            <button onClick={() => saveEdit(field.field_name)} className="btn-primary" title="Save">Save</button>
                            <button onClick={() => setEditingField(null)} className="btn-ghost" aria-label="Cancel">Cancel</button>
                          </div>
                        ) : (
                          <>
                            <div className="field-value" onDoubleClick={() => startEditing(field)}>
                              {field.value || '<empty>'}
                            </div>
                            <div className="field-confidence">
                              Confidence: {(field.confidence * 100).toFixed(1)}%
                              {field.is_corrected && <span className="ml-2 badge-warning">Corrected</span>}
                            </div>
                            <button onClick={() => startEditing(field)} className="btn-ghost p-1 ml-2" aria-label="Edit field"><Edit className="w-4 h-4" /></button>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Flags Section */}
            {(reviewDoc?.fraud_flags && reviewDoc.fraud_flags.length > 0) && (
              <div className="p-4 border-t border-slate-200">
                <h4 className="font-semibold text-slate-900 mb-3">Fraud Flags</h4>
                <div className="space-y-3">
                  {reviewDoc.fraud_flags.map((flag: FraudFlag) => (
                    <div key={flag.id} className={clsx('flag-card', `flag-${flag.severity}`)}>
                      <div className="flag-header">
                        <span className="flag-title">{flag.flag_type.replace(/_/g, ' ')}</span>
                        <span className={clsx('flag-severity', `severity-${flag.severity}`)}>{flag.severity}</span>
                      </div>
                      <div className="flag-details">
                        <pre className="whitespace-pre-wrap text-xs">{JSON.stringify(flag.details, null, 2)}</pre>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(reviewDoc?.rule_violations && reviewDoc.rule_violations.length > 0) && (
              <div className="p-4 border-t border-slate-200">
                <h4 className="font-semibold text-slate-900 mb-3">Rule Violations</h4>
                <div className="space-y-2">
                  {reviewDoc.rule_violations.map((violation: RuleViolation) => (
                    <div key={violation.id} className="card p-3">
                      <p className="font-medium text-slate-900">{String(violation.details.rule_name || 'Rule Violation')}</p>
                      <pre className="text-sm text-slate-600 mt-1 whitespace-pre-wrap">{JSON.stringify(violation.details, null, 2)}</pre>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(reviewDoc?.duplicate_flags && reviewDoc.duplicate_flags.length > 0) && (
              <div className="p-4 border-t border-slate-200">
                <h4 className="font-semibold text-slate-900 mb-3">Duplicate Matches</h4>
                <div className="space-y-2">
                  {reviewDoc.duplicate_flags.map((dup: DuplicateFlag) => (
                    <div key={dup.id} className="card p-3">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">Match: {dup.match_type}</span>
                        <span className="badge-primary">{Math.round(dup.confidence_score * 100)}% confidence</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}