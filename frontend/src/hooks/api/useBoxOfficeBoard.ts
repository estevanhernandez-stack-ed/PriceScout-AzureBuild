import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

export type BoardResolution = '720p' | '1080p' | '4k' | 'letter';

export const RESOLUTION_LABELS: Record<BoardResolution, string> = {
  '720p': '720p (1280×720)',
  '1080p': '1080p (1920×1080)',
  '4k': '4K (3840×2160)',
  'letter': 'Letter Landscape (Print)',
};

// ============================================================================
// Hook: Fetch board HTML for iframe preview
// ============================================================================

/**
 * Fetch the box office board HTML for a theater + date.
 *
 * Returns the raw HTML string which can be rendered in an iframe via srcdoc.
 *
 * @param theater - Theater name (exact match)
 * @param date - Date in YYYY-MM-DD format
 * @param resolution - Target resolution preset
 * @param enabled - Whether the query should run
 */
export function useBoxOfficeBoard(
  theater: string,
  date: string,
  resolution: BoardResolution = '1080p',
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: ['reports', 'box-office-board', theater, date, resolution],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('theater', theater);
      params.append('date', date);
      params.append('resolution', resolution);
      params.append('output_format', 'html');

      const response = await api.get(
        `/reports/box-office-board?${params.toString()}`,
        { responseType: 'text' },
      );
      return response.data as string;
    },
    enabled: enabled && !!theater && !!date,
    staleTime: 10 * 60 * 1000, // 10 min — schedule doesn't change often
  });
}

// ============================================================================
// Download helpers (called imperatively, not as hooks)
// ============================================================================

/**
 * Download the board as an HTML file for loading on a display screen.
 */
export async function downloadBoardHtml(
  theater: string,
  date: string,
  resolution: BoardResolution,
): Promise<void> {
  const params = new URLSearchParams();
  params.append('theater', theater);
  params.append('date', date);
  params.append('resolution', resolution);
  params.append('output_format', 'html');

  const response = await api.get(
    `/reports/box-office-board?${params.toString()}`,
    { responseType: 'text' },
  );

  const blob = new Blob([response.data], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `BoxOfficeBoard_${theater.replace(/\s+/g, '_')}_${date}_${resolution}.html`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Download the board as a PNG image.
 */
export async function downloadBoardImage(
  theater: string,
  date: string,
  resolution: BoardResolution,
): Promise<void> {
  const params = new URLSearchParams();
  params.append('theater', theater);
  params.append('date', date);
  params.append('resolution', resolution);
  params.append('output_format', 'image');

  const response = await api.get(
    `/reports/box-office-board?${params.toString()}`,
    { responseType: 'blob' },
  );

  const url = URL.createObjectURL(response.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = `BoxOfficeBoard_${theater.replace(/\s+/g, '_')}_${date}_${resolution}.png`;
  a.click();
  URL.revokeObjectURL(url);
}
