'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useUploadDocument, useDocumentSessionPolling } from '@/hooks/useQueries';
import { Upload, Loader2, CheckCircle, AlertCircle, X, FileText, ChevronDown, ChevronUp } from 'lucide-react';
import clsx from 'clsx';

const ACCEPTED_TYPES = [
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/tiff',
  'image/tif',
];

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadMutation = useUploadDocument();
  const { data: sessionData, isLoading: sessionLoading } = useDocumentSessionPolling(
    uploadMutation.data?.document_id || '',
    !!uploadMutation.data?.document_id
  );

  const uploadDocument = useCallback(async (file: File) => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError('Invalid file type. Please upload PDF, JPEG, PNG, or TIFF.');
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      setError('File size exceeds 20MB limit.');
      return;
    }

    setError(null);
    setFile(file);
    try {
      await uploadMutation.mutateAsync(file);
    } catch (err) {
      setError('Upload failed. Please try again.');
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragActive(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadDocument(file);
  }, [uploadDocument]);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragActive(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragActive(false);
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadDocument(file);
  }, [uploadDocument]);

  const handleRemoveFile = useCallback(() => {
    setFile(null);
    setError(null);
  }, []);

  // Determine current stage from session data
  const currentStage = sessionData?.current_stage || 'uploaded';
  const progress = sessionData?.progress_percent || 0;
  const stageHistory = sessionData?.stage_history || [];

  const stageConfig: Record<string, { label: string; order: number }> = {
    uploaded: { label: 'Uploaded', order: 1 },
    ocr_processing: { label: 'OCR Processing', order: 2 },
    extracting: { label: 'Extracting Fields', order: 3 },
    quality_gate: { label: 'Quality Gate', order: 4 },
    duplicate_check: { label: 'Duplicate Check', order: 5 },
    evaluate_rules: { label: 'Rule Evaluation', order: 6 },
    fraud_check: { label: 'Fraud Check', order: 7 },
    three_way_match: { label: '3-Way Match', order: 8 },
    review: { label: 'Review', order: 9 },
    verified: { label: 'Verified', order: 10 },
  };

  const stages = Object.entries(stageConfig)
    .sort((a, b) => a[1].order - b[1].order)
    .map(([key, config]) => ({ key, ...config }));

  const currentStageIndex = stages.findIndex(s => s.key === currentStage);
  const completedStages = stages.filter((_, i) => i <= currentStageIndex);
  const currentStageConfig = stageConfig[currentStage] || { label: 'Processing', order: 0 };

  if (uploadMutation.isPending) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <div className="card p-8 text-center">
            <div className="mx-auto w-12 h-12 border-4 border-primary-600 border-t-transparent rounded-full animate-spin mb-6" />
            <h2 className="text-xl font-semibold text-slate-900">Uploading Document...</h2>
            <p className="text-slate-600 mt-2">Please wait while we upload your document</p>
          </div>
        </div>
      </div>
    );
  }

  if (uploadMutation.isError) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <div className="card p-8 text-center">
            <div className="mx-auto w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path d="M6 18L18 6M6 6l12 12" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-slate-900">Upload Failed</h2>
            <p className="text-slate-600 mt-2">{uploadMutation.error?.message || 'Upload failed. Please try again.'}</p>
            <button
              onClick={() => router.push('/upload')}
              className="btn-primary w-full mt-6"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  const isComplete = uploadMutation.isSuccess && sessionData?.current_stage === 'verified';
  const isProcessing = uploadMutation.isSuccess && !isComplete;

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Upload Document</h1>
          <p className="text-slate-600 mt-1">Upload an invoice or document for processing</p>
        </div>

        {/* Upload Zone */}
        {!file && (
          <div
            className={clsx(
              'upload-zone',
              isDragActive && 'active'
            )}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click(); }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_TYPES.join(',')}
              onChange={handleFileSelect}
              className="hidden"
              id="file-upload"
            />
            <div className="space-y-4">
              <div className="w-16 h-16 mx-auto bg-primary-100 rounded-full flex items-center justify-center text-primary-600">
                <Upload className="w-8 h-8" />
              </div>
              <div>
                <p className="text-lg font-medium text-slate-900">Drag & drop your file here</p>
                <p className="text-slate-600 mt-1">or click to browse</p>
                <p className="text-sm text-slate-500 mt-2">
                  PDF, JPEG, PNG, TIFF up to 20MB
                </p>
              </div>
            </div>
          </div>
        )}

        {/* File Preview */}
        {file && (
          <div className="card mb-6 overflow-hidden">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={clsx(
                  'w-12 h-12 rounded-lg flex items-center justify-center',
                  file.type === 'application/pdf' ? 'bg-red-100 text-red-600' :
                  file.type.startsWith('image/') ? 'bg-green-100 text-green-600' :
                  'bg-blue-100 text-blue-600'
                )}>
                  {file.type === 'application/pdf' ? (
                    <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="currentColor"/><path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  ) : (
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L14 14"/></svg>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-slate-900 truncate">{file.name}</p>
                  <p className="text-sm text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                </div>
              </div>
              <button
                onClick={handleRemoveFile}
                className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                aria-label="Remove file"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>
            </div>
          </div>
        )}

        {/* Progress Section */}
        {(isProcessing || isComplete) && (
          <div className="card mb-6 overflow-hidden">
            <div className="p-4 border-b border-slate-200">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-semibold text-slate-900">
                  {isComplete ? 'Processing Complete' : 'Processing Document'}
                </h3>
                {isComplete && (
                  <span className="badge-success">Completed</span>
                )}
              </div>
              <div className="progress-bar">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${progress}%` }}
                  role="progressbar"
                  aria-valuenow={progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
              <p className="text-sm text-slate-600 mt-2">
                {isComplete
                  ? 'Document processing complete. Redirecting...'
                  : `Stage: ${stageConfig[currentStage]?.label || currentStage} (${progress}%)`}
              </p>
            </div>

            {/* Stage History */}
            {stageHistory.length > 0 && (
              <div className="border-t border-slate-200">
                <div className="p-4">
                  <h4 className="font-medium text-slate-900 mb-3">Processing Stages</h4>
                  <div className="space-y-2">
                    {stages.map((stage) => {
                      const historyEntry = stageHistory.find((h: { stage: string; progress: number; timestamp: string; message: string }) => h.stage === stage.key);
                      const isCompleted = historyEntry !== undefined;
                      const isCurrent = stage.key === currentStage;
                      return (
                        <div
                          key={stage.key}
                          className={clsx(
                            'flex items-center gap-3 p-2 rounded-lg transition-colors',
                            isCompleted ? 'bg-success-50' : 'bg-slate-50',
                            isCurrent && 'bg-primary-50 ring-1 ring-primary-200'
                          )}
                        >
                          <div className={clsx(
                            'w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0',
                            isCompleted ? 'bg-success-600 text-white' :
                            isCurrent ? 'bg-primary-600 text-white' : 'bg-slate-200 text-slate-400'
                          )}>
                            {isCompleted ? (
                              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414z" clipRule="evenodd"/></svg>
                            ) : isCurrent ? (
                              <div className="w-2 h-2 bg-current bg-primary-600 rounded-full animate-pulse" />
                            ) : (
                              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L11.586 10l-4.293 4.293a1 1 0 001.414 1.414l4-4a1 1 0 000-1.414l-4-4a1 1 0 00-1.414 0l-4 4a1 1 0 000 1.414l4 4a1 1 0 001.414 0z" clipRule="evenodd"/></svg>
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-slate-900">{stage.label}</p>
                            {historyEntry && (
                              <p className="text-sm text-slate-500">
                                Completed at {new Date(historyEntry.timestamp).toLocaleTimeString()}
                              </p>
                            )}
                          </div>
                          {isCurrent && (
                            <span className="badge-primary text-xs animate-pulse">Current</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Upload Form */}
        {!file && !isProcessing && !isComplete && (
          <div className="text-center">
            <p className="text-slate-500 mb-4">Supported formats: PDF, JPEG, PNG, TIFF (max 20MB)</p>
          </div>
        )}

        {error && (
          <div className="mb-6 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700 text-sm" role="alert">
            <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 11-2 0 1 1 0 012 0z" clipRule="evenodd"/></svg>
            <span>{error}</span>
          </div>
        )}

        {isComplete && (
          <div className="text-center mt-6">
            <div className="mx-auto w-16 h-16 bg-success-100 rounded-full flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-success-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M16 4v12l-8 5-4-4-4 4-4-4 4-4 4 4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </div>
            <h3 className="text-xl font-semibold text-slate-900 mb-2">Document Processed Successfully</h3>
            <p className="text-slate-600 mb-6">Your document has been processed and verified.</p>
            <button
              onClick={() => router.push(`/documents/${uploadMutation.data?.document_id}`)}
              className="btn-primary"
            >
              View Document
            </button>
          </div>
        )}
      </div>
    </div>
  );
}