import type { GetServerSideProps } from 'next';
import Head from 'next/head';
import { useState } from 'react';

interface HealthResponse {
  status: string;
  service: string;
  version?: string;
}

interface PageProps {
  apiHealth: HealthResponse;
  frontendHealth: HealthResponse;
}

export default function Home({ apiHealth, frontendHealth }: PageProps) {
  return (
    <div style={styles.container}>
      <Head>
        <title>Audit-AI - Document Intelligence Platform</title>
        <meta name="description" content="Audit-AI Document Intelligence Platform" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <main style={styles.main}>
        <h1 style={styles.title}>Audit-AI</h1>
        <p style={styles.description}>Document Intelligence Platform</p>

        <div style={styles.grid}>
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>API Service</h2>
            <div style={styles.status}>
              <span style={{
                ...styles.statusDot,
                backgroundColor: apiHealth.status === 'ok' ? '#22c55e' : '#ef4444'
              }} />
              <span style={styles.statusText}>
                {apiHealth.status === 'ok' ? 'Healthy' : 'Unhealthy'}
              </span>
            </div>
            <p style={styles.cardInfo}>Version: {apiHealth.version || 'unknown'}</p>
            <p style={styles.cardInfo}>Service: {apiHealth.service}</p>
          </div>

          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Frontend Service</h2>
            <div style={styles.status}>
              <span style={{
                ...styles.statusDot,
                backgroundColor: frontendHealth.status === 'ok' ? '#22c55e' : '#ef4444'
              }} />
              <span style={styles.statusText}>
                {frontendHealth.status === 'ok' ? 'Healthy' : 'Unhealthy'}
              </span>
            </div>
            <p style={styles.cardInfo}>Service: {frontendHealth.service}</p>
          </div>

          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Worker Service</h2>
            <div style={styles.status}>
              <span style={{
                ...styles.statusDot,
                backgroundColor: '#f59e0b'
              }} />
              <span style={styles.statusText}>Not checked from frontend</span>
            </div>
            <p style={styles.cardInfo}>Check via docker-compose logs</p>
          </div>
        </div>

        <div style={styles.links}>
          <a href="/api/docs" target="_blank" rel="noopener noreferrer" style={styles.link}>
            API Documentation (Swagger)
          </a>
          <a href="/health" target="_blank" rel="noopener noreferrer" style={styles.link}>
            Health Endpoint
          </a>
        </div>
      </main>

      <footer style={styles.footer}>
        <p>Audit-AI v0.1.0 - Monorepo Scaffold</p>
      </footer>
    </div>
  );
}

export const getServerSideProps: GetServerSideProps<PageProps> = async ({ req }) => {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  
  let apiHealth: HealthResponse = { status: 'unknown', service: 'api' };
  let frontendHealth: HealthResponse = { status: 'ok', service: 'frontend' };

  try {
    const res = await fetch(`${apiUrl}/health`, {
      headers: { 'Accept': 'application/json' },
      // Timeout after 5 seconds
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      apiHealth = await res.json();
    } else {
      apiHealth = { status: 'error', service: 'api' };
    }
  } catch {
    apiHealth = { status: 'error', service: 'api' };
  }

  return {
    props: {
      apiHealth,
      frontendHealth,
    },
  };
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    backgroundColor: '#f8fafc',
    color: '#1e293b',
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '4rem 2rem',
    maxWidth: '1200px',
    margin: '0 auto',
    width: '100%',
  },
  title: {
    fontSize: '3.5rem',
    fontWeight: 700,
    marginBottom: '0.5rem',
    background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  description: {
    fontSize: '1.25rem',
    color: '#64748b',
    marginBottom: '3rem',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
    gap: '1.5rem',
    width: '100%',
    maxWidth: '900px',
    marginBottom: '2rem',
  },
  card: {
    background: 'white',
    borderRadius: '12px',
    padding: '1.5rem',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    border: '1px solid #e2e8f0',
  },
  cardTitle: {
    fontSize: '1.125rem',
    fontWeight: 600,
    marginBottom: '1rem',
    color: '#1e293b',
  },
  status: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    marginBottom: '1rem',
  },
  statusDot: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
  },
  statusText: {
    fontSize: '0.875rem',
    fontWeight: 500,
  },
  cardInfo: {
    fontSize: '0.875rem',
    color: '#64748b',
    marginBottom: '0.5rem',
  },
  links: {
    display: 'flex',
    gap: '1.5rem',
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  link: {
    color: '#3b82f6',
    textDecoration: 'none',
    fontWeight: 500,
    padding: '0.5rem 1rem',
    border: '1px solid #3b82f6',
    borderRadius: '6px',
    transition: 'all 0.2s',
  },
  footer: {
    padding: '2rem',
    textAlign: 'center',
    color: '#94a3b8',
    fontSize: '0.875rem',
    borderTop: '1px solid #e2e8f0',
  },
};