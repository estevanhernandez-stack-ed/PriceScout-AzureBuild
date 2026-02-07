import { describe, it, expect } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import {
  useUsers,
  useUser,
  useCreateUser,
  useUpdateUser,
  useDeleteUser,
  useChangePassword,
  useResetPassword,
} from './useUsers';
import { createWrapper } from '@/test/utils';

describe('useUsers hooks', () => {
  describe('useUsers', () => {
    it('fetches users list', async () => {
      const { result } = renderHook(() => useUsers(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        users: expect.any(Array),
        total_count: expect.any(Number),
      });
    });

    it('returns users with expected structure', async () => {
      const { result } = renderHook(() => useUsers(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      const user = result.current.data?.users[0];
      expect(user).toMatchObject({
        user_id: expect.any(Number),
        username: expect.any(String),
        role: expect.any(String),
      });
    });

    it('supports role filter', async () => {
      const { result } = renderHook(() => useUsers({ role: 'admin' }), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('useUser', () => {
    it('fetches single user by ID', async () => {
      const { result } = renderHook(() => useUser(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        user_id: expect.any(Number),
        username: expect.any(String),
      });
    });

    it('is disabled without user ID', async () => {
      const { result } = renderHook(() => useUser(0), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useCreateUser', () => {
    it('creates a new user', async () => {
      const { result } = renderHook(() => useCreateUser(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          username: 'newuser',
          password: 'password123',
          role: 'user',
          company: 'Test Company',
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        user_id: expect.any(Number),
        username: expect.any(String),
      });
    });
  });

  describe('useUpdateUser', () => {
    it('updates an existing user', async () => {
      const { result } = renderHook(() => useUpdateUser(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          userId: 1,
          data: { username: 'updateduser' },
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useDeleteUser', () => {
    it('deletes a user', async () => {
      const { result } = renderHook(() => useDeleteUser(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate(1);
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useChangePassword', () => {
    it('changes user password', async () => {
      const { result } = renderHook(() => useChangePassword(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          old_password: 'oldpass',
          new_password: 'newpass123',
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        message: expect.any(String),
      });
    });
  });

  describe('useResetPassword', () => {
    it('resets user password (admin)', async () => {
      const { result } = renderHook(() => useResetPassword(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          userId: 1,
          data: { new_password: 'resetpass123' },
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toMatchObject({
        message: expect.any(String),
      });
    });
  });
});
