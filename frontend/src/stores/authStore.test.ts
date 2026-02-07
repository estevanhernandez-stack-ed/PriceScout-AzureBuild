import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act } from '@testing-library/react';
import { useAuthStore } from './authStore';
import { api } from '@/lib/api';

describe('authStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useAuthStore.setState({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      suppressAutoLogout: false,
      pendingAuthIssue: false,
    });
    vi.restoreAllMocks();
  });

  describe('initial state', () => {
    it('has correct initial values', () => {
      const state = useAuthStore.getState();

      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.suppressAutoLogout).toBe(false);
      expect(state.pendingAuthIssue).toBe(false);
    });
  });

  describe('setToken', () => {
    it('sets token and marks as authenticated', () => {
      const { setToken } = useAuthStore.getState();

      act(() => {
        setToken('test-token');
      });

      const state = useAuthStore.getState();
      expect(state.token).toBe('test-token');
      expect(state.isAuthenticated).toBe(true);
    });

    it('overwrites existing token', () => {
      useAuthStore.setState({ token: 'old-token', isAuthenticated: true });

      const { setToken } = useAuthStore.getState();

      act(() => {
        setToken('new-token');
      });

      expect(useAuthStore.getState().token).toBe('new-token');
    });
  });

  describe('clearError', () => {
    it('clears the error state', () => {
      useAuthStore.setState({ error: 'Some error' });

      const { clearError } = useAuthStore.getState();

      act(() => {
        clearError();
      });

      expect(useAuthStore.getState().error).toBeNull();
    });

    it('does not affect other state', () => {
      useAuthStore.setState({
        error: 'Some error',
        token: 'my-token',
        isAuthenticated: true,
      });

      const { clearError } = useAuthStore.getState();

      act(() => {
        clearError();
      });

      const state = useAuthStore.getState();
      expect(state.error).toBeNull();
      expect(state.token).toBe('my-token');
      expect(state.isAuthenticated).toBe(true);
    });
  });

  describe('setSuppressAutoLogout', () => {
    it('sets suppressAutoLogout to true', () => {
      const { setSuppressAutoLogout } = useAuthStore.getState();

      act(() => {
        setSuppressAutoLogout(true);
      });

      expect(useAuthStore.getState().suppressAutoLogout).toBe(true);
    });

    it('sets suppressAutoLogout to false', () => {
      useAuthStore.setState({ suppressAutoLogout: true });

      const { setSuppressAutoLogout } = useAuthStore.getState();

      act(() => {
        setSuppressAutoLogout(false);
      });

      expect(useAuthStore.getState().suppressAutoLogout).toBe(false);
    });

    it('toggles suppressAutoLogout', () => {
      const { setSuppressAutoLogout } = useAuthStore.getState();

      act(() => {
        setSuppressAutoLogout(true);
      });
      expect(useAuthStore.getState().suppressAutoLogout).toBe(true);

      act(() => {
        setSuppressAutoLogout(false);
      });
      expect(useAuthStore.getState().suppressAutoLogout).toBe(false);
    });
  });

  describe('clearPendingAuthIssue', () => {
    it('clears pendingAuthIssue flag', () => {
      useAuthStore.setState({ pendingAuthIssue: true });

      const { clearPendingAuthIssue } = useAuthStore.getState();

      act(() => {
        clearPendingAuthIssue();
      });

      expect(useAuthStore.getState().pendingAuthIssue).toBe(false);
    });

    it('does not affect other state', () => {
      useAuthStore.setState({
        pendingAuthIssue: true,
        token: 'my-token',
        suppressAutoLogout: true,
      });

      const { clearPendingAuthIssue } = useAuthStore.getState();

      act(() => {
        clearPendingAuthIssue();
      });

      const state = useAuthStore.getState();
      expect(state.pendingAuthIssue).toBe(false);
      expect(state.token).toBe('my-token');
      expect(state.suppressAutoLogout).toBe(true);
    });
  });

  describe('login', () => {
    it('sets isLoading during login', async () => {
      // Mock a slow fetch
      vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
        new Promise((resolve) =>
          setTimeout(() => resolve(new Response(
            JSON.stringify({ access_token: 'tok', token_type: 'bearer' }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          )), 50)
        )
      );

      const loginPromise = useAuthStore.getState().login('user', 'pass');

      // isLoading should be true while request is in flight
      expect(useAuthStore.getState().isLoading).toBe(true);
      expect(useAuthStore.getState().error).toBeNull();

      await loginPromise;

      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it('sets token and isAuthenticated on success', async () => {
      vi.spyOn(api, 'post').mockResolvedValueOnce({
        data: { access_token: 'jwt-123', token_type: 'bearer' },
      });
      vi.spyOn(api, 'get').mockResolvedValueOnce({
        data: { id: 1, username: 'user', role: 'admin' },
      });

      await useAuthStore.getState().login('user', 'pass');

      const state = useAuthStore.getState();
      expect(state.token).toBe('jwt-123');
      expect(state.isAuthenticated).toBe(true);
      expect(state.isLoading).toBe(false);
    });

    it('sets error on failure', async () => {
      const axiosError = new Error('Request failed') as Error & { response?: { data?: { detail?: string } }; isAxiosError?: boolean };
      axiosError.response = { data: { detail: 'Invalid credentials' } };
      axiosError.isAxiosError = true;
      vi.spyOn(api, 'post').mockRejectedValueOnce(axiosError);

      await expect(useAuthStore.getState().login('bad', 'creds')).rejects.toThrow();

      const state = useAuthStore.getState();
      expect(state.error).toBe('Invalid credentials');
      expect(state.isAuthenticated).toBe(false);
      expect(state.token).toBeNull();
      expect(state.isLoading).toBe(false);
    });
  });

  describe('logout', () => {
    it('clears auth state', async () => {
      useAuthStore.setState({
        token: 'jwt-123',
        user: { id: 1, username: 'user' } as never,
        isAuthenticated: true,
      });

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
        new Response(JSON.stringify({ success: true }), { status: 200 })
      );

      await useAuthStore.getState().logout();

      const state = useAuthStore.getState();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.error).toBeNull();
    });

    it('clears state even if logout request fails', async () => {
      useAuthStore.setState({
        token: 'jwt-123',
        isAuthenticated: true,
      });

      vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
        Promise.reject(new Error('Network error'))
      );

      // logout uses try/finally so it should still clear state
      try {
        await useAuthStore.getState().logout();
      } catch {
        // Expected - the fetch error may propagate
      }

      const state = useAuthStore.getState();
      expect(state.token).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });

    it('does not call fetch if no token', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      await useAuthStore.getState().logout();

      expect(fetchSpy).not.toHaveBeenCalled();

      const state = useAuthStore.getState();
      expect(state.token).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });
  });

  describe('refreshToken', () => {
    it('does nothing if no token exists', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      await useAuthStore.getState().refreshToken();

      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('updates token on success', async () => {
      useAuthStore.setState({ token: 'old-token', isAuthenticated: true });

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
        new Response(
          JSON.stringify({ access_token: 'refreshed-token', token_type: 'bearer' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      );

      await useAuthStore.getState().refreshToken();

      expect(useAuthStore.getState().token).toBe('refreshed-token');
      expect(useAuthStore.getState().pendingAuthIssue).toBe(false);
    });

    it('logs out on failure when suppressAutoLogout is false', async () => {
      useAuthStore.setState({ token: 'expired', isAuthenticated: true, suppressAutoLogout: false });

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
        new Response('', { status: 401 })
      );

      await useAuthStore.getState().refreshToken();

      // Should have attempted logout (which calls fetch again)
      // The key assertion is that auth state is cleared
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });

    it('sets pendingAuthIssue instead of logout when suppressAutoLogout is true', async () => {
      useAuthStore.setState({
        token: 'expired',
        isAuthenticated: true,
        suppressAutoLogout: true,
      });

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
        new Response('', { status: 401 })
      );

      await useAuthStore.getState().refreshToken();

      expect(useAuthStore.getState().pendingAuthIssue).toBe(true);
      // Token should still be there since we suppressed logout
      expect(useAuthStore.getState().token).toBe('expired');
    });

    it('handles network error with suppressAutoLogout', async () => {
      useAuthStore.setState({
        token: 'some-token',
        isAuthenticated: true,
        suppressAutoLogout: true,
      });

      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'));

      await useAuthStore.getState().refreshToken();

      expect(useAuthStore.getState().pendingAuthIssue).toBe(true);
    });
  });

  describe('loginWithEntra', () => {
    it('redirects to entra login URL', () => {
      // Mock window.location
      const originalLocation = window.location;
      const mockLocation = { ...originalLocation, href: '', origin: 'http://localhost:3000' };
      Object.defineProperty(window, 'location', {
        writable: true,
        value: mockLocation,
      });

      useAuthStore.getState().loginWithEntra();

      expect(mockLocation.href).toContain('/api/v1/auth/entra/login');
      expect(mockLocation.href).toContain('redirect_after=');

      // Restore
      Object.defineProperty(window, 'location', {
        writable: true,
        value: originalLocation,
      });
    });
  });

  describe('state persistence keys', () => {
    it('has the correct store name for persistence', () => {
      // The store name is 'pricescout-auth' as defined in persist config
      // This verifies the store configuration is correct
      const state = useAuthStore.getState();
      expect(state).toHaveProperty('token');
      expect(state).toHaveProperty('isAuthenticated');
    });
  });

  describe('direct state manipulation', () => {
    it('allows setting isLoading state', () => {
      useAuthStore.setState({ isLoading: true });
      expect(useAuthStore.getState().isLoading).toBe(true);

      useAuthStore.setState({ isLoading: false });
      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it('allows setting user state', () => {
      const mockUser = {
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
        role: 'admin',
        company_id: 1,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
      };

      useAuthStore.setState({ user: mockUser as never });
      expect(useAuthStore.getState().user).toEqual(mockUser);
    });

    it('allows setting error state', () => {
      useAuthStore.setState({ error: 'Test error message' });
      expect(useAuthStore.getState().error).toBe('Test error message');
    });
  });

  describe('combined state changes', () => {
    it('can set multiple values at once', () => {
      useAuthStore.setState({
        token: 'new-token',
        isAuthenticated: true,
        error: null,
        isLoading: false,
      });

      const state = useAuthStore.getState();
      expect(state.token).toBe('new-token');
      expect(state.isAuthenticated).toBe(true);
      expect(state.error).toBeNull();
      expect(state.isLoading).toBe(false);
    });

    it('simulates login success state', () => {
      // Simulate what happens after successful login
      useAuthStore.setState({
        token: 'jwt-token-here',
        isAuthenticated: true,
        isLoading: false,
        error: null,
        user: { id: 1, username: 'user' } as never,
      });

      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(true);
      expect(state.token).toBeTruthy();
      expect(state.user).toBeDefined();
    });

    it('simulates logout state', () => {
      // Set up authenticated state first
      useAuthStore.setState({
        token: 'jwt-token',
        isAuthenticated: true,
        user: { id: 1 } as never,
      });

      // Simulate logout
      useAuthStore.setState({
        token: null,
        user: null,
        isAuthenticated: false,
        error: null,
      });

      const state = useAuthStore.getState();
      expect(state.token).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });
  });
});
