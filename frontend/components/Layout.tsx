'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useTier } from '@/hooks/useQueries';
import clsx from 'clsx';
import {
  LayoutDashboard,
  Upload,
  FileSearch,
  Settings,
  LogOut,
  ChevronRight,
  ChevronLeft,
  Shield,
  FileText,
  BarChart3,
  Menu,
  X,
} from 'lucide-react';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard, feature: null },
  { name: 'Upload', href: '/upload', icon: Upload, feature: null },
  { name: 'Documents', href: '/documents', icon: FileSearch, feature: null },
  { name: 'Review Queue', href: '/review', icon: Shield, feature: 'nl_query' },
  { name: 'Rules', href: '/rules', icon: FileText, feature: 'rules_engine' },
  { name: 'Ask AI', href: '/ask', icon: BarChart3, feature: 'nl_query' },
  { name: 'Reports', href: '/reports', icon: BarChart3, feature: 'reporting' },
  { name: '3-Way Match', href: '/three-way-match', icon: BarChart3, feature: 'three_way_match' },
  { name: 'Settings', href: '/settings', icon: Settings, feature: null },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { data: tier } = useTier();
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  const enabledFeatures = tier?.features || {};

  const filteredNavigation = navigation.filter((item) => {
    if (!item.feature) return true;
    return enabledFeatures[item.feature];
  });

  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={clsx(
          'sidebar transition-all duration-300 z-40',
          collapsed ? 'w-16' : 'w-64',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        {/* Logo */}
        <div className={clsx('p-4 border-b border-slate-200 flex items-center justify-between', collapsed && 'justify-center')}>
          <Link href="/" className="flex items-center gap-2" style={{ display: collapsed ? 'none' : 'flex' }}>
            <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </div>
            <span className="font-bold text-xl text-slate-900">Audit-AI</span>
          </Link>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 transition-colors lg:hidden"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M9 18l6-6-6-6" /></svg> : <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><path d="M15 18l-6-6 6-6" /></svg>}
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          {navigation.filter((item) => {
            if (!item.feature) return true;
            return enabledFeatures[item.feature];
          }).map((item) => {
            const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`nav-item ${isActive ? 'active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
              >
                <item.icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
                <span style={{ display: collapsed ? 'none' : 'inline' }}>{item.name}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 flex items-center justify-between" style={{ flexDirection: collapsed ? 'column' : 'row', alignItems: collapsed ? 'center' : 'flex-start' }}>
          <div style={{ display: collapsed ? 'none' : 'flex', flex: 1, minWidth: 0 }}>
            <p className="text-sm font-medium text-slate-900 truncate">{user?.email}</p>
            <p className="text-xs text-slate-500 capitalize truncate">{user?.role}</p>
          </div>
          <button
            onClick={() => {
              const { logout } = useAuth();
              logout();
              window.location.href = '/login';
            }}
            className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
            aria-label="Log out"
            title="Log out"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </svg>
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      <button
        className="lg:hidden fixed bottom-4 right-4 z-50 p-3 bg-primary-600 text-white rounded-full shadow-lg hover:bg-primary-700 transition-colors"
        onClick={() => setMobileOpen(true)}
        aria-label="Open menu"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
          <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
        </svg>
      </button>
    </>
  );
}