import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { useAuthStore } from '@/stores/authStore';

// Mock the auth store
vi.mock('@/stores/authStore', () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = vi.mocked(useAuthStore);

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithRouter = (ui: React.ReactElement, initialEntry = '/protected') => {
    return render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/protected" element={ui} />
        </Routes>
      </MemoryRouter>
    );
  };

  describe('authentication checks', () => {
    it('shows loading spinner while checking auth', () => {
      mockUseAuthStore.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: true,
      } as ReturnType<typeof useAuthStore>);

      renderWithRouter(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      );

      // Should show spinner (animate-spin class)
      const spinner = document.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
    });

    it('redirects to login when not authenticated', () => {
      mockUseAuthStore.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false,
      } as ReturnType<typeof useAuthStore>);

      renderWithRouter(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByText('Login Page')).toBeInTheDocument();
    });

    it('renders children when authenticated', () => {
      mockUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: { id: 1, username: 'test', role: 'user' },
        isLoading: false,
      } as ReturnType<typeof useAuthStore>);

      renderWithRouter(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByText('Protected Content')).toBeInTheDocument();
    });
  });

  describe('role-based access', () => {
    it('allows access when user has required role', () => {
      mockUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: { id: 1, username: 'admin', role: 'admin' },
        isLoading: false,
      } as ReturnType<typeof useAuthStore>);

      renderWithRouter(
        <ProtectedRoute requiredRole="admin">
          <div>Admin Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByText('Admin Content')).toBeInTheDocument();
    });

    it('denies access when user lacks required role', () => {
      mockUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: { id: 1, username: 'user', role: 'user' },
        isLoading: false,
      } as ReturnType<typeof useAuthStore>);

      renderWithRouter(
        <ProtectedRoute requiredRole="admin">
          <div>Admin Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByText('Access Denied')).toBeInTheDocument();
      expect(screen.queryByText('Admin Content')).not.toBeInTheDocument();
    });

    it('admin bypasses all role checks', () => {
      mockUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: { id: 1, username: 'admin', role: 'admin' },
        isLoading: false,
      } as ReturnType<typeof useAuthStore>);

      renderWithRouter(
        <ProtectedRoute requiredRole="operator">
          <div>Operator Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByText('Operator Content')).toBeInTheDocument();
    });

    it('supports array of required roles', () => {
      mockUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: { id: 1, username: 'operator', role: 'operator' },
        isLoading: false,
      } as ReturnType<typeof useAuthStore>);

      renderWithRouter(
        <ProtectedRoute requiredRole={['admin', 'operator']}>
          <div>Multi-Role Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByText('Multi-Role Content')).toBeInTheDocument();
    });

    it('respects role hierarchy (manager > user)', () => {
      mockUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: { id: 1, username: 'manager', role: 'manager' },
        isLoading: false,
      } as ReturnType<typeof useAuthStore>);

      renderWithRouter(
        <ProtectedRoute requiredRole="user">
          <div>User Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByText('User Content')).toBeInTheDocument();
    });

    it('shows current and required role in access denied message', () => {
      mockUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: { id: 1, username: 'user', role: 'user' },
        isLoading: false,
      } as ReturnType<typeof useAuthStore>);

      renderWithRouter(
        <ProtectedRoute requiredRole="admin">
          <div>Admin Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByText(/Required role: admin/)).toBeInTheDocument();
      expect(screen.getByText(/Your role: user/)).toBeInTheDocument();
    });
  });
});
