import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';
import type {
  UserResponse,
  UserCreate,
  UserUpdate,
  UserList,
  PasswordChange,
  PasswordReset,
} from '@/types';

interface UserFilters {
  role?: string;
  isActive?: boolean;
  limit?: number;
  offset?: number;
}

/**
 * Fetch users with filters
 */
export function useUsers(filters: UserFilters = {}) {
  return useQuery({
    queryKey: queryKeys.users.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.role) params.append('role', filters.role);
      if (filters.isActive !== undefined)
        params.append('is_active', String(filters.isActive));
      if (filters.limit) params.append('limit', String(filters.limit));
      if (filters.offset) params.append('offset', String(filters.offset));

      const response = await api.get<UserList>(`/users?${params.toString()}`);
      return response.data;
    },
  });
}

/**
 * Fetch a single user by ID
 */
export function useUser(userId: number) {
  return useQuery({
    queryKey: queryKeys.users.detail(userId),
    queryFn: async () => {
      const response = await api.get<UserResponse>(`/users/${userId}`);
      return response.data;
    },
    enabled: !!userId,
  });
}

/**
 * Create a new user (admin only)
 */
export function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: UserCreate) => {
      const response = await api.post<UserResponse>('/users', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
    },
  });
}

/**
 * Update a user
 */
export function useUpdateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      userId,
      data,
    }: {
      userId: number;
      data: UserUpdate;
    }) => {
      const response = await api.put<UserResponse>(`/users/${userId}`, data);
      return response.data;
    },
    onSuccess: (_, { userId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(userId) });
    },
  });
}

/**
 * Delete a user (admin only)
 */
export function useDeleteUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (userId: number) => {
      await api.delete(`/users/${userId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all });
    },
  });
}

/**
 * Change own password
 */
export function useChangePassword() {
  return useMutation({
    mutationFn: async (data: PasswordChange) => {
      const response = await api.post<{ message: string }>(
        '/auth/change-password',
        data
      );
      return response.data;
    },
  });
}

/**
 * Reset user password (admin only)
 */
export function useResetPassword() {
  return useMutation({
    mutationFn: async ({
      userId,
      data,
    }: {
      userId: number;
      data: PasswordReset;
    }) => {
      const response = await api.post<{ message: string }>(
        `/users/${userId}/reset-password`,
        data
      );
      return response.data;
    },
  });
}
