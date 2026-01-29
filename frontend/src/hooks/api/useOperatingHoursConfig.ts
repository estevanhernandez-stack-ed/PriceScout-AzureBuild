import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';

export interface DailyOperatingHours {
  day_of_week: number;
  open_time: string | null;
  close_time: string | null;
  first_showtime: string | null;
  last_showtime: string | null;
}

export interface TheaterOperatingHoursUpdate {
  theater_name: string;
  hours: DailyOperatingHours[];
}

export function useTheaterOperatingHours(theaterName: string | null) {
  return useQuery({
    queryKey: ['market-context', 'operating-hours', theaterName],
    queryFn: async () => {
      if (!theaterName) return [];
      const response = await api.get<DailyOperatingHours[]>(
        `/market-context/operating-hours?theater_name=${encodeURIComponent(theaterName)}`
      );
      return response.data;
    },
    enabled: !!theaterName,
  });
}

export function useUpdateTheaterOperatingHours() {
  return useMutation({
    mutationFn: async (update: TheaterOperatingHoursUpdate) => {
      const response = await api.post('/market-context/operating-hours', update);
      return response.data;
    },
  });
}
