import { useEffect, useRef } from 'react';
import { jwtDecode } from 'jwt-decode';
import { useAuthStore } from '@/stores/authStore';

interface JWTPayload {
  exp: number;
  sub: string;
}

export function useTokenRefresh() {
  const { token, fetchUser, refreshToken, logout, suppressAutoLogout } = useAuthStore();
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();

  // Re-fetch user profile on mount when we have a token (keeps role/company fresh after refresh)
  useEffect(() => {
    if (token) {
      fetchUser();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- run once on mount

  useEffect(() => {
    if (!token) {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      return;
    }

    try {
      const decoded = jwtDecode<JWTPayload>(token);
      const expiresAt = decoded.exp * 1000; // Convert to milliseconds
      const now = Date.now();

      // Refresh 5 minutes before expiration
      const refreshIn = expiresAt - now - 5 * 60 * 1000;

      if (refreshIn <= 0) {
        // Token already expired or about to expire
        refreshToken();
      } else {
        // Schedule refresh
        timeoutRef.current = setTimeout(() => {
          refreshToken();
        }, refreshIn);
      }
    } catch {
      // Invalid token - respect suppression flag during long operations
      if (suppressAutoLogout) {
        console.log('[TokenRefresh] Invalid token, but auto-logout is suppressed');
        useAuthStore.setState({ pendingAuthIssue: true });
      } else {
        logout();
      }
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [token, refreshToken, logout, suppressAutoLogout]);
}
