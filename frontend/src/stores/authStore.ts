import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { UserResponse, Token } from '@/types';
import { api } from '@/lib/api';

interface AuthState {
  // State
  token: string | null;
  user: UserResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  // Suppress auto-logout during long-running operations (e.g., scrapes)
  suppressAutoLogout: boolean;
  // Track if there's a pending auth issue that needs attention
  pendingAuthIssue: boolean;

  // Actions
  login: (username: string, password: string) => Promise<void>;
  loginWithEntra: () => void;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
  fetchUser: () => Promise<void>;
  clearError: () => void;
  setToken: (token: string) => void;
  setSuppressAutoLogout: (suppress: boolean) => void;
  clearPendingAuthIssue: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      suppressAutoLogout: false,
      pendingAuthIssue: false,

      // Login with username/password
      login: async (username: string, password: string) => {
        set({ isLoading: true, error: null });

        try {
          const formData = new URLSearchParams();
          formData.append('username', username);
          formData.append('password', password);

          const response = await fetch('/api/v1/auth/token', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData,
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
          }

          const data: Token = await response.json();
          set({ token: data.access_token, isAuthenticated: true });

          // Fetch user profile
          await get().fetchUser();
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Login failed',
            isAuthenticated: false,
            token: null,
          });
          throw error;
        } finally {
          set({ isLoading: false });
        }
      },

      // Initiate Entra ID login
      loginWithEntra: () => {
        const returnUrl = encodeURIComponent(window.location.origin + '/auth/callback');
        window.location.href = `/api/v1/auth/entra/login?redirect_after=${returnUrl}`;
      },

      // Set token (for Entra callback)
      setToken: (token: string) => {
        set({ token, isAuthenticated: true });
      },

      // Logout
      logout: async () => {
        const { token } = get();

        try {
          if (token) {
            await fetch('/api/v1/auth/logout', {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${token}`,
              },
            });
          }
        } finally {
          set({
            token: null,
            user: null,
            isAuthenticated: false,
            error: null,
          });
        }
      },

      // Refresh token
      refreshToken: async () => {
        const { token, suppressAutoLogout } = get();
        if (!token) return;

        try {
          const response = await fetch('/api/v1/auth/refresh', {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });

          if (response.ok) {
            const data: Token = await response.json();
            set({ token: data.access_token, pendingAuthIssue: false });
          } else {
            // Token expired
            if (suppressAutoLogout) {
              // Don't logout during long operations, just flag the issue
              console.log('[Auth] Token refresh failed, but auto-logout is suppressed');
              set({ pendingAuthIssue: true });
            } else {
              await get().logout();
            }
          }
        } catch {
          if (suppressAutoLogout) {
            console.log('[Auth] Token refresh error, but auto-logout is suppressed');
            set({ pendingAuthIssue: true });
          } else {
            await get().logout();
          }
        }
      },

      // Fetch current user
      fetchUser: async () => {
        const { token } = get();
        if (!token) return;

        try {
          const response = await api.get<UserResponse>('/auth/me');
          set({ user: response.data });
        } catch {
          // Silent fail - user fetch is optional
        }
      },

      clearError: () => set({ error: null }),

      // Control auto-logout suppression (for long-running operations like scrapes)
      setSuppressAutoLogout: (suppress: boolean) => {
        console.log('[Auth] Setting suppressAutoLogout:', suppress);
        set({ suppressAutoLogout: suppress });
      },

      // Clear pending auth issue (after user acknowledges or re-authenticates)
      clearPendingAuthIssue: () => set({ pendingAuthIssue: false }),
    }),
    {
      name: 'pricescout-auth',
      partialize: (state) => ({
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
