'use client';

import React, { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useNLQuery, useNLQueryHistory, NLQueryHistoryItem } from '@/hooks/useQueries';
import { FeatureGate } from '@/components/FeatureGate';
import { Send, Bot, History, X } from 'lucide-react';
import clsx from 'clsx';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  structuredData?: unknown;
  intent?: string;
  timestamp: Date;
}

function isTabular(data: unknown): data is Array<Record<string, unknown>> {
  return (
    Array.isArray(data) &&
    data.length > 0 &&
    data.every((row) => row !== null && typeof row === 'object' && !Array.isArray(row))
  );
}

function StructuredDataView({ data }: { data: unknown }) {
  if (isTabular(data)) {
    const columns = Array.from(
      new Set(data.flatMap((row) => Object.keys(row)))
    );
    return (
      <div className="mt-3 overflow-x-auto border border-slate-200 rounded-lg">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{col.replace(/_/g, ' ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i}>
                {columns.map((col) => (
                  <td key={col} className="font-mono text-xs">
                    {row[col] === null || row[col] === undefined ? '—' : String(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <details className="mt-3">
      <summary className="text-sm font-medium text-slate-600 cursor-pointer">View structured data</summary>
      <pre className="mt-2 p-3 bg-slate-100 rounded-lg text-xs overflow-x-auto text-slate-800">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

function AskAIPageInner() {
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'Hello! I can help you query your document data. Try asking things like:\n\n• "How much have we paid Acme Corp this year?"\n• "What is the average tax rate this quarter?"\n• "Show me flagged documents from last month"\n• "Who are our top 5 vendors by spend?"',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [viewingHistoryId, setViewingHistoryId] = useState<string | null>(null);

  const nlQueryMutation = useNLQuery();
  const { data: history, isLoading: historyLoading } = useNLQueryHistory(showHistory);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const question = input;
    setMessages((prev) => [...prev, { role: 'user', content: question, timestamp: new Date() }]);
    setViewingHistoryId(null);
    setInput('');
    setIsLoading(true);

    try {
      const result = await nlQueryMutation.mutateAsync(question);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: result.answer,
          structuredData: result.structured_data ?? undefined,
          intent: result.intent,
          timestamp: new Date(),
        },
      ]);
      queryClient.invalidateQueries({ queryKey: ['nlQueryHistory'] });
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, I encountered an error processing your question. Please try again.',
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const viewHistoryItem = (item: NLQueryHistoryItem) => {
    setViewingHistoryId(item.id);
    setMessages([
      { role: 'user', content: item.question, timestamp: new Date(item.created_at || Date.now()) },
      {
        role: 'assistant',
        content: item.answer || '(no answer recorded)',
        intent: item.intent || undefined,
        timestamp: new Date(item.created_at || Date.now()),
      },
    ]);
    setShowHistory(false);
  };

  const backToLiveChat = () => {
    setViewingHistoryId(null);
    setMessages([
      {
        role: 'assistant',
        content: 'Back to live chat. Ask me anything about your documents.',
        timestamp: new Date(),
      },
    ]);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <header className="top-bar">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
            <Bot className="w-5 h-5 text-primary-600" />
            Ask AI
          </h1>
          <span className="badge-primary">NL Query</span>
          {viewingHistoryId && (
            <button onClick={backToLiveChat} className="btn-ghost text-sm">
              ← Back to live chat
            </button>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="btn-ghost"
            aria-label="Toggle history"
            title="Query history"
          >
            {showHistory ? <X className="w-5 h-5" /> : <History className="w-5 h-5" />}
          </button>
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {messages.map((message, index) => (
              <div key={index} className={clsx('flex gap-3', message.role === 'user' && 'flex-row-reverse')}>
                <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-primary-100 text-primary-600">
                  {message.role === 'user' ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /></svg>
                  ) : (
                    <Bot className="w-5 h-5" />
                  )}
                </div>
                <div
                  className={clsx(
                    'max-w-[70%] px-4 py-3 rounded-2xl',
                    message.role === 'user'
                      ? 'bg-primary-600 text-white rounded-tr-none'
                      : 'bg-white border border-slate-200 rounded-tl-none'
                  )}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                  {message.structuredData !== undefined && message.structuredData !== null && (
                    <StructuredDataView data={message.structuredData} />
                  )}
                  {message.intent && <p className="mt-2 text-xs text-slate-500">Intent: {message.intent}</p>}
                  <p className="mt-2 text-xs text-slate-400">
                    {message.timestamp.toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {!viewingHistoryId && (
            <div className="border-t border-slate-200 p-4 bg-white">
              <form onSubmit={handleSubmit} className="flex gap-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSubmit(e as unknown as React.FormEvent<HTMLFormElement>);
                    }
                  }}
                  placeholder="Ask a question about your documents..."
                  className="input flex-1 resize-none"
                  rows={1}
                  style={{ minHeight: '48px', maxHeight: '200px' }}
                  disabled={isLoading}
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading}
                  className="btn-primary p-3 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
                  aria-label="Send message"
                >
                  <Send className="w-5 h-5" />
                </button>
              </form>
            </div>
          )}
        </div>

        {showHistory && (
          <aside className="w-80 bg-white border-l border-slate-200 flex flex-col shrink-0">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-semibold text-slate-900">Past questions</h3>
              <button onClick={() => setShowHistory(false)} className="p-1 text-slate-400 hover:text-slate-600" aria-label="Close history">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {historyLoading ? (
                <p className="p-4 text-sm text-slate-500">Loading history...</p>
              ) : !history || history.length === 0 ? (
                <p className="p-4 text-sm text-slate-500">No past questions yet. Ask something to get started.</p>
              ) : (
                history.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => viewHistoryItem(item)}
                    className={clsx(
                      'w-full text-left p-3 rounded-lg hover:bg-slate-100 transition-colors',
                      viewingHistoryId === item.id && 'bg-primary-50'
                    )}
                  >
                    <p className="text-sm font-medium text-slate-900 truncate">{item.question}</p>
                    <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                      {item.intent && <span className="badge-gray">{item.intent}</span>}
                      {item.created_at && <span>{new Date(item.created_at).toLocaleString()}</span>}
                    </p>
                  </button>
                ))
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

export default function AskAIPage() {
  return (
    <FeatureGate feature="nl_query">
      <AskAIPageInner />
    </FeatureGate>
  );
}
