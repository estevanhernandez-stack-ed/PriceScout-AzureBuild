import { describe, it, expect, beforeEach } from 'vitest';
import { act } from '@testing-library/react';
import { useBackgroundJobsStore } from './backgroundJobsStore';

describe('backgroundJobsStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useBackgroundJobsStore.setState({ backgroundJobIds: [] });
  });

  describe('initial state', () => {
    it('starts with an empty backgroundJobIds array', () => {
      const state = useBackgroundJobsStore.getState();
      expect(state.backgroundJobIds).toEqual([]);
    });
  });

  describe('sendToBackground', () => {
    it('adds a job ID to the list', () => {
      act(() => {
        useBackgroundJobsStore.getState().sendToBackground(101);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([101]);
    });

    it('adds multiple job IDs', () => {
      act(() => {
        useBackgroundJobsStore.getState().sendToBackground(1);
        useBackgroundJobsStore.getState().sendToBackground(2);
        useBackgroundJobsStore.getState().sendToBackground(3);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([1, 2, 3]);
    });

    it('does not add duplicate job IDs', () => {
      act(() => {
        useBackgroundJobsStore.getState().sendToBackground(42);
        useBackgroundJobsStore.getState().sendToBackground(42);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([42]);
    });

    it('does not add duplicate when job already exists', () => {
      useBackgroundJobsStore.setState({ backgroundJobIds: [10, 20] });

      act(() => {
        useBackgroundJobsStore.getState().sendToBackground(10);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([10, 20]);
    });
  });

  describe('removeFromBackground', () => {
    it('removes a job ID from the list', () => {
      useBackgroundJobsStore.setState({ backgroundJobIds: [1, 2, 3] });

      act(() => {
        useBackgroundJobsStore.getState().removeFromBackground(2);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([1, 3]);
    });

    it('does nothing if job ID is not in the list', () => {
      useBackgroundJobsStore.setState({ backgroundJobIds: [1, 2, 3] });

      act(() => {
        useBackgroundJobsStore.getState().removeFromBackground(999);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([1, 2, 3]);
    });

    it('handles removing from an empty list', () => {
      act(() => {
        useBackgroundJobsStore.getState().removeFromBackground(1);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([]);
    });

    it('removes the only job, leaving an empty list', () => {
      useBackgroundJobsStore.setState({ backgroundJobIds: [5] });

      act(() => {
        useBackgroundJobsStore.getState().removeFromBackground(5);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([]);
    });
  });

  describe('clearFinished', () => {
    it('removes all finished job IDs from the list', () => {
      useBackgroundJobsStore.setState({ backgroundJobIds: [1, 2, 3, 4, 5] });

      act(() => {
        useBackgroundJobsStore.getState().clearFinished([2, 4]);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([1, 3, 5]);
    });

    it('handles empty finished list (no-op)', () => {
      useBackgroundJobsStore.setState({ backgroundJobIds: [1, 2, 3] });

      act(() => {
        useBackgroundJobsStore.getState().clearFinished([]);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([1, 2, 3]);
    });

    it('handles clearing IDs that are not in the background list', () => {
      useBackgroundJobsStore.setState({ backgroundJobIds: [1, 2] });

      act(() => {
        useBackgroundJobsStore.getState().clearFinished([99, 100]);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([1, 2]);
    });

    it('clears all jobs when all are finished', () => {
      useBackgroundJobsStore.setState({ backgroundJobIds: [10, 20, 30] });

      act(() => {
        useBackgroundJobsStore.getState().clearFinished([10, 20, 30]);
      });

      expect(useBackgroundJobsStore.getState().backgroundJobIds).toEqual([]);
    });
  });
});
