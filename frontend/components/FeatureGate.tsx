'use client';

import React from 'react';
import ErrorPage from 'next/error';
import { useTier } from '@/hooks/useQueries';

/**
 * Renders children only when the given tier feature is enabled.
 * While the tier is loading, shows a spinner. When the feature is
 * disabled, renders the real Next.js 404 page (not just a hidden nav) so
 * direct navigation 404s on tiers without the feature.
 */
export function FeatureGate({
  feature,
  children,
}: {
  feature: string;
  children: React.ReactNode;
}) {
  const { data: tier, isLoading, error } = useTier();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const enabled = (tier?.features as Record<string, boolean> | undefined)?.[feature] === true;
  if (!enabled || error) {
    return <ErrorPage statusCode={404} />;
  }

  return <>{children}</>;
}
