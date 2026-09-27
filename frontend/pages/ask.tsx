'use client';

import React, { useState, useCallback } from 'react';
import { useNLQuery } from '@/hooks/useQueries';
import { Send, Loader2, Bot, X, Copy, ChevronUp, ChevronDown, Menu, X as XIcon } from 'lucide-react';
import clsx from 'clsx';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  structuredData?: Record<string, unknown>;
  intent?: string;
  timestamp: Date;
}

export default function AskAIPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'Hello! I can help you query your document data. Try asking things like:\n\n• "How much have we paid Acme Corp this year?"\n• "What is the average tax rate this quarter?"\n• "Show me flagged documents from last month"\n• "Give me a summary of invoice INV-001"\n• "Who are our top 5 vendors by spend?"',
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const nlQueryMutation = useNLQuery();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    const question = input;
    setInput('');
    setIsLoading(true);

    try {
      const result = await nlQueryMutation.mutateAsync(question);
      const assistantMessage: Message = {
        role: 'assistant',
        content: result.answer,
        structuredData: result.structured_data || undefined,
        intent: result.intent,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      const errorMessage: Message = {
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your question. Please try again.',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="top-bar">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
            <svg className="w-5 h-5 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M12 8V4H8"/><rect x="8" y="14" width="16" height="12" rx="2"/><path d="M12 18h.01"/></svg>
            Ask AI
          </h1>
          <span className="badge-primary">NL Query</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="btn-ghost"
            aria-label="Toggle history"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
          </button>
        </div>
      </header>

      <div className="flex-1 flex flex-col">
        {/* Chat Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
{messages.map((message, index) => (
            <React.Fragment key={index}>
              <div className={clsx('flex gap-3', message.role === 'user' && 'flex-row-reverse')}>
                <div className={clsx(
                  'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
                  message.role === 'user' ? 'bg-primary-100 text-primary-600' : 'bg-primary-100 text-primary-600'
                )}>
                  {message.role === 'user' ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/></svg>
                  ) : (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 8V4H8"/><rect x="8" y="14" width="16" height="12" rx="2"/><path d="M12 18h.01"/></svg>
                  )}
                </div>
                <div className={clsx(
                  'max-w-[70%] px-4 py-3 rounded-2xl',
                  message.role === 'user' ? 'bg-primary-600 text-white rounded-tr-none' : 'bg-white border border-slate-200 rounded-tr-none'
                )}>
                  <div className="prose prose-sm max-w-none">
                    <p className="whitespace-pre-wrap">{message.content}</p>
                    {message.structuredData && (
                      <details className="mt-3">
                        <summary className="text-sm font-medium text-slate-600 cursor-pointer">View structured data</summary>
                        <pre className="mt-2 p-3 bg-slate-100 rounded-lg text-xs overflow-x-auto text-slate-800">
                          {JSON.stringify(message.structuredData, null, 2)}
                        </pre>
                      </details>
                    )}
                    {message.intent && (
                      <p className="mt-2 text-xs text-slate-500">Intent: {message.intent}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-2 opacity-0 group-hover:opacity-100">
                    {message.structuredData && (
                      <button
                        onClick={() => navigator.clipboard.writeText(JSON.stringify(message.structuredData, null, 2))}
                        className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                        title="Copy JSON"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M16 16v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2h2"/></svg>
                      </button>
                    )}
                    <span className="text-xs text-slate-400">{new Date(message.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
              </div>
            </React.Fragment>
          ))}
        </div>

        {/* Input Area */}
        <div className="border-t border-slate-200 p-4 bg-white">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <div className="relative flex-1">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e as unknown as React.FormEvent<HTMLFormElement>); }}}
                placeholder="Ask a question about your documents..."
                className="w-full px-4 py-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent resize-none"
                rows={1}
                style={{ minHeight: '48px', maxHeight: '200px' }}
                disabled={isLoading}
              />
              {isLoading && (
                <div className="absolute right-4 top-1/2 -translate-y-1/2">
                  <svg className="w-5 h-5 text-primary-600 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" strokeWidth="3" strokeDasharray="30 90" strokeLinecap="round"/></svg>
                </div>
              )}
            </div>
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="btn-primary p-3 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Send message"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-8 18 18"/></svg>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}