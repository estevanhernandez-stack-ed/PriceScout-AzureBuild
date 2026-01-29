import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryClient';

// =============================================================================
// TYPES
// =============================================================================

export interface DiscountProgram {
  program_id: number;
  circuit_name: string;
  program_name: string;
  day_of_week: number;
  day_name: string;
  discount_type: 'flat_price' | 'percentage_off' | 'amount_off';
  discount_value: number;
  applicable_ticket_types: string[] | null;
  applicable_formats: string[] | null;
  applicable_dayparts: string[] | null;
  is_active: boolean;
  confidence_score: number;
  sample_count: number;
  source: string;
  discovered_at: string;
  last_verified_at: string | null;
}

export interface CreateDiscountProgramRequest {
  program_name: string;
  day_of_week: number;
  discount_type: 'flat_price' | 'percentage_off' | 'amount_off';
  discount_value: number;
  applicable_ticket_types?: string[];
  applicable_formats?: string[];
  applicable_dayparts?: string[];
}

export interface ProfileGap {
  gap_id: number;
  gap_type: 'format' | 'ticket_type' | 'daypart';
  expected_value: string;
  reason: string | null;
  first_detected_at: string;
  resolved_at: string | null;
  resolution_notes: string | null;
  is_resolved: boolean;
}

export interface ResolveGapRequest {
  resolution_notes?: string;
}

export interface CompanyProfile {
  profile_id: number;
  circuit_name: string;
  version: number;
  is_current: boolean;
  discovered_at: string;
  last_updated_at: string;
  ticket_types: string[];
  daypart_scheme: string;
  daypart_labels: Record<string, string>;
  format_upcharges: Record<string, number>;
  theater_count: number;
  sample_count: number;
  confidence_score: number;
}

// =============================================================================
// DISCOUNT PROGRAMS HOOKS
// =============================================================================

/**
 * List discount programs for a circuit
 */
export function useDiscountPrograms(circuitName: string, activeOnly = true, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.companyProfiles.discountPrograms(circuitName),
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('active_only', String(activeOnly));
      const response = await api.get<DiscountProgram[]>(
        `/company-profiles/${encodeURIComponent(circuitName)}/discount-programs?${params.toString()}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? !!circuitName,
  });
}

/**
 * Create or update a discount program
 */
export function useCreateDiscountProgram() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      circuitName,
      ...request
    }: CreateDiscountProgramRequest & { circuitName: string }) => {
      const response = await api.post<DiscountProgram>(
        `/company-profiles/${encodeURIComponent(circuitName)}/discount-programs`,
        request
      );
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.companyProfiles.discountPrograms(data.circuit_name),
      });
    },
  });
}

/**
 * Delete (deactivate) a discount program
 */
export function useDeleteDiscountProgram() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      circuitName,
      programId,
    }: {
      circuitName: string;
      programId: number;
    }) => {
      const response = await api.delete<{ message: string }>(
        `/company-profiles/${encodeURIComponent(circuitName)}/discount-programs/${programId}`
      );
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.companyProfiles.discountPrograms(variables.circuitName),
      });
    },
  });
}

// =============================================================================
// PROFILE GAPS HOOKS
// =============================================================================

/**
 * List gaps for a circuit profile
 */
export function useProfileGaps(circuitName: string, includeResolved = false, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.companyProfiles.gaps(circuitName),
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('include_resolved', String(includeResolved));
      const response = await api.get<ProfileGap[]>(
        `/company-profiles/${encodeURIComponent(circuitName)}/gaps?${params.toString()}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? !!circuitName,
  });
}

/**
 * Resolve a profile gap
 */
export function useResolveGap() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      circuitName,
      gapId,
      ...request
    }: ResolveGapRequest & { circuitName: string; gapId: number }) => {
      const response = await api.post<ProfileGap>(
        `/company-profiles/${encodeURIComponent(circuitName)}/gaps/${gapId}/resolve`,
        request
      );
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.companyProfiles.gaps(variables.circuitName),
      });
    },
  });
}

// =============================================================================
// PROFILE VERSIONS HOOKS
// =============================================================================

/**
 * List all versions of a profile
 */
export function useProfileVersions(circuitName: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.companyProfiles.versions(circuitName),
    queryFn: async () => {
      const response = await api.get<CompanyProfile[]>(
        `/company-profiles/${encodeURIComponent(circuitName)}/versions`
      );
      return response.data;
    },
    enabled: options?.enabled ?? !!circuitName,
  });
}

// =============================================================================
// COMPANY PROFILES HOOKS
// =============================================================================

/**
 * List all company profiles
 */
export function useCompanyProfiles() {
  return useQuery({
    queryKey: queryKeys.companyProfiles.list(),
    queryFn: async () => {
      const response = await api.get<{ total: number; profiles: CompanyProfile[] }>(
        '/company-profiles'
      );
      return response.data;
    },
  });
}

/**
 * Get a single company profile by circuit name
 */
export function useCompanyProfile(circuitName: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.companyProfiles.detail(circuitName),
    queryFn: async () => {
      const response = await api.get<CompanyProfile>(
        `/company-profiles/${encodeURIComponent(circuitName)}`
      );
      return response.data;
    },
    enabled: options?.enabled ?? !!circuitName,
  });
}
