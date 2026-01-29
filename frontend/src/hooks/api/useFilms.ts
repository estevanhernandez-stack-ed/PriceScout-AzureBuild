import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

export interface FilmMetadata {
  film_title: string;
  imdb_id?: string;
  genre?: string;
  mpaa_rating?: string;
  director?: string;
  actors?: string;
  plot?: string;
  poster_url?: string;
  metascore?: number;
  imdb_rating?: number;
  release_date?: string;
  domestic_gross?: number;
  runtime?: string;
  opening_weekend_domestic?: number;
  last_omdb_update?: string;
  first_play_date?: string; // Augmented on frontend usually or from special helper
}

export function useFilms() {
  return useQuery({
    queryKey: ['films'],
    queryFn: async () => {
      const response = await api.get<FilmMetadata[]>('/films');
      return response.data;
    },
  });
}

export function useEnrichFilm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (filmTitle: string) => {
      const response = await api.post(`/films/${encodeURIComponent(filmTitle)}/enrich`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['films'] });
    },
  });
}

export function useDiscoverFandango() {
  return useMutation({
    mutationFn: async () => {
      const response = await api.post('/films/discover/fandango');
      return response.data;
    },
  });
}
