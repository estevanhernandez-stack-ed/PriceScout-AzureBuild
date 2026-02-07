import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface BackgroundJobsState {
  /** Job IDs that the user has sent to background */
  backgroundJobIds: number[];

  /** Move a scrape job to background tracking */
  sendToBackground: (jobId: number) => void;

  /** Remove a job from background tracking (dismissed by user) */
  removeFromBackground: (jobId: number) => void;

  /** Remove all completed/failed jobs from tracking */
  clearFinished: (finishedJobIds: number[]) => void;
}

export const useBackgroundJobsStore = create<BackgroundJobsState>()(
  persist(
    (set) => ({
      backgroundJobIds: [],

      sendToBackground: (jobId: number) =>
        set((state) => ({
          backgroundJobIds: state.backgroundJobIds.includes(jobId)
            ? state.backgroundJobIds
            : [...state.backgroundJobIds, jobId],
        })),

      removeFromBackground: (jobId: number) =>
        set((state) => ({
          backgroundJobIds: state.backgroundJobIds.filter((id) => id !== jobId),
        })),

      clearFinished: (finishedJobIds: number[]) =>
        set((state) => ({
          backgroundJobIds: state.backgroundJobIds.filter(
            (id) => !finishedJobIds.includes(id)
          ),
        })),
    }),
    {
      name: 'pricescout-background-jobs',
    }
  )
);
