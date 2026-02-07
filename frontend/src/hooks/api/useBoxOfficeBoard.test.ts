import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import {
  useBoxOfficeBoard,
  RESOLUTION_LABELS,
  downloadBoardHtml,
  downloadBoardImage,
} from './useBoxOfficeBoard';
import type { BoardResolution } from './useBoxOfficeBoard';
import { createWrapper } from '@/test/utils';

describe('useBoxOfficeBoard hooks', () => {
  describe('useBoxOfficeBoard', () => {
    it('fetches box office board HTML', async () => {
      const { result } = renderHook(
        () => useBoxOfficeBoard('AMC Madison 6', '2026-01-20', '1080p'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
      expect(typeof result.current.data).toBe('string');
    });

    it('is disabled when theater is empty', () => {
      const { result } = renderHook(
        () => useBoxOfficeBoard('', '2026-01-20'),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('is disabled when date is empty', () => {
      const { result } = renderHook(
        () => useBoxOfficeBoard('AMC Madison 6', ''),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('is disabled when enabled is false', () => {
      const { result } = renderHook(
        () => useBoxOfficeBoard('AMC Madison 6', '2026-01-20', '1080p', false),
        { wrapper: createWrapper() }
      );

      expect(result.current.fetchStatus).toBe('idle');
    });

    it('accepts different resolution presets', async () => {
      const { result } = renderHook(
        () => useBoxOfficeBoard('AMC Madison 6', '2026-01-20', '4k'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });

    it('uses 1080p as default resolution', async () => {
      const { result } = renderHook(
        () => useBoxOfficeBoard('AMC Madison 6', '2026-01-20'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeDefined();
    });
  });

  describe('RESOLUTION_LABELS', () => {
    it('contains all resolution presets', () => {
      expect(RESOLUTION_LABELS).toMatchObject({
        '720p': expect.any(String),
        '1080p': expect.any(String),
        '4k': expect.any(String),
        'letter': expect.any(String),
      });
    });

    it('has exactly 4 resolution presets', () => {
      const keys = Object.keys(RESOLUTION_LABELS);
      expect(keys).toHaveLength(4);
    });

    it('has descriptive labels with dimensions', () => {
      expect(RESOLUTION_LABELS['720p']).toContain('1280');
      expect(RESOLUTION_LABELS['1080p']).toContain('1920');
      expect(RESOLUTION_LABELS['4k']).toContain('3840');
      expect(RESOLUTION_LABELS['letter']).toContain('Letter');
    });
  });

  describe('downloadBoardHtml', () => {
    it('creates a download link and clicks it', async () => {
      // jsdom doesn't have URL.createObjectURL - define mocks directly
      const mockUrl = 'blob:http://localhost/mock-blob';
      const createObjectURLMock = vi.fn().mockReturnValue(mockUrl);
      const revokeObjectURLMock = vi.fn();
      URL.createObjectURL = createObjectURLMock;
      URL.revokeObjectURL = revokeObjectURLMock;

      // Mock document.createElement to capture the anchor click
      const mockAnchor = {
        href: '',
        download: '',
        click: vi.fn(),
      };
      const origCreateElement = document.createElement.bind(document);
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        if (tag === 'a') return mockAnchor as unknown as HTMLAnchorElement;
        return origCreateElement(tag);
      });

      await downloadBoardHtml('AMC Madison 6', '2026-01-20', '1080p');

      expect(createObjectURLMock).toHaveBeenCalled();
      expect(mockAnchor.click).toHaveBeenCalled();
      expect(mockAnchor.download).toContain('BoxOfficeBoard_AMC_Madison_6_2026-01-20_1080p.html');
      expect(revokeObjectURLMock).toHaveBeenCalledWith(mockUrl);

      vi.restoreAllMocks();
    });
  });

  describe('downloadBoardImage', () => {
    it('creates a download link for PNG and clicks it', async () => {
      const mockUrl = 'blob:http://localhost/mock-image-blob';
      const createObjectURLMock = vi.fn().mockReturnValue(mockUrl);
      const revokeObjectURLMock = vi.fn();
      URL.createObjectURL = createObjectURLMock;
      URL.revokeObjectURL = revokeObjectURLMock;

      const mockAnchor = {
        href: '',
        download: '',
        click: vi.fn(),
      };
      const origCreateElement = document.createElement.bind(document);
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        if (tag === 'a') return mockAnchor as unknown as HTMLAnchorElement;
        return origCreateElement(tag);
      });

      await downloadBoardImage('AMC Madison 6', '2026-01-20', '4k');

      expect(createObjectURLMock).toHaveBeenCalled();
      expect(mockAnchor.click).toHaveBeenCalled();
      expect(mockAnchor.download).toContain('BoxOfficeBoard_AMC_Madison_6_2026-01-20_4k.png');
      expect(revokeObjectURLMock).toHaveBeenCalledWith(mockUrl);

      vi.restoreAllMocks();
    });
  });

  describe('BoardResolution type', () => {
    it('accepts valid resolution values', () => {
      const resolutions: BoardResolution[] = ['720p', '1080p', '4k', 'letter'];
      resolutions.forEach((res) => {
        expect(RESOLUTION_LABELS[res]).toBeDefined();
      });
    });
  });
});
