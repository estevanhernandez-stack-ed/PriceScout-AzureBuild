import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act } from '@testing-library/react';
import { useToast } from './use-toast';

describe('useToast store', () => {
  beforeEach(() => {
    // Reset store state before each test
    useToast.setState({ toasts: [] });
    vi.useFakeTimers();
  });

  // Clean up fake timers after the suite runs
  // (vitest auto-restores per-test, but let's be explicit)

  describe('initial state', () => {
    it('starts with an empty toasts array', () => {
      const state = useToast.getState();
      expect(state.toasts).toEqual([]);
    });

    it('has toast and dismiss functions', () => {
      const state = useToast.getState();
      expect(typeof state.toast).toBe('function');
      expect(typeof state.dismiss).toBe('function');
    });
  });

  describe('toast', () => {
    it('adds a toast with generated id', () => {
      act(() => {
        useToast.getState().toast({ title: 'Hello' });
      });

      const toasts = useToast.getState().toasts;
      expect(toasts).toHaveLength(1);
      expect(toasts[0].title).toBe('Hello');
      expect(toasts[0].id).toBeDefined();
      expect(typeof toasts[0].id).toBe('string');
    });

    it('adds a toast with description', () => {
      act(() => {
        useToast.getState().toast({ title: 'Title', description: 'Desc' });
      });

      const toasts = useToast.getState().toasts;
      expect(toasts[0].description).toBe('Desc');
    });

    it('adds a toast with destructive variant', () => {
      act(() => {
        useToast.getState().toast({ title: 'Error', variant: 'destructive' });
      });

      const toasts = useToast.getState().toasts;
      expect(toasts[0].variant).toBe('destructive');
    });

    it('adds multiple toasts', () => {
      act(() => {
        useToast.getState().toast({ title: 'First' });
        useToast.getState().toast({ title: 'Second' });
        useToast.getState().toast({ title: 'Third' });
      });

      expect(useToast.getState().toasts).toHaveLength(3);
    });

    it('assigns unique IDs to each toast', () => {
      act(() => {
        useToast.getState().toast({ title: 'A' });
        useToast.getState().toast({ title: 'B' });
      });

      const [a, b] = useToast.getState().toasts;
      expect(a.id).not.toBe(b.id);
    });

    it('auto-dismisses after 5 seconds', () => {
      act(() => {
        useToast.getState().toast({ title: 'Auto dismiss me' });
      });

      expect(useToast.getState().toasts).toHaveLength(1);

      act(() => {
        vi.advanceTimersByTime(5000);
      });

      expect(useToast.getState().toasts).toHaveLength(0);
    });

    it('does not auto-dismiss before 5 seconds', () => {
      act(() => {
        useToast.getState().toast({ title: 'Waiting' });
      });

      act(() => {
        vi.advanceTimersByTime(4999);
      });

      expect(useToast.getState().toasts).toHaveLength(1);
    });
  });

  describe('dismiss', () => {
    it('removes a toast by id', () => {
      act(() => {
        useToast.getState().toast({ title: 'Dismissable' });
      });

      const toastId = useToast.getState().toasts[0].id;

      act(() => {
        useToast.getState().dismiss(toastId);
      });

      expect(useToast.getState().toasts).toHaveLength(0);
    });

    it('only removes the targeted toast', () => {
      act(() => {
        useToast.getState().toast({ title: 'Keep me' });
        useToast.getState().toast({ title: 'Remove me' });
      });

      const toasts = useToast.getState().toasts;
      const removeId = toasts[1].id;

      act(() => {
        useToast.getState().dismiss(removeId);
      });

      const remaining = useToast.getState().toasts;
      expect(remaining).toHaveLength(1);
      expect(remaining[0].title).toBe('Keep me');
    });

    it('does nothing when id does not exist', () => {
      act(() => {
        useToast.getState().toast({ title: 'Existing' });
      });

      act(() => {
        useToast.getState().dismiss('nonexistent-id');
      });

      expect(useToast.getState().toasts).toHaveLength(1);
    });
  });
});
