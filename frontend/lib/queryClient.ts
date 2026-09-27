'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { ReactNode, useRef, createElement, Fragment } from 'react';

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const queryClientRef = useRef<QueryClient | null>(null);

  if (!queryClientRef.current) {
    const defaultOptions = {
      queries: {
        staleTime: 1000 * 60 * 5, // 5 minutes
        gcTime: 1000 * 60 * 30, // 30 minutes (formerly cacheTime)
        retry: 1,
        refetchOnWindowFocus: false
      }
    };
    queryClientRef.current = new QueryClient({
      defaultOptions
    });
  }

  const client = queryClientRef.current!;

  return createElement(
    QueryClientProvider,
    { client },
    createElement(Fragment, null, children),
    createElement(ReactQueryDevtools, { initialIsOpen: false })
  );
}