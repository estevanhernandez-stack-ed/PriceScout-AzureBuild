/**
 * PriceScout API Hooks - Barrel Export
 *
 * TanStack Query hooks for all API endpoints.
 *
 * Usage:
 * import { usePriceAlerts, useAcknowledgeAlert } from '@/hooks/api';
 */

// Price Checks
export {
  usePriceChecks,
  useLatestPrices,
  usePriceCheckSummary,
  usePriceComparison,
} from './usePriceChecks';
export * from './useAnalytics';

// Price Alerts
export {
  usePriceAlerts,
  usePendingAlerts,
  useAlertSummary,
  usePriceAlert,
  useAcknowledgeAlert,
  useBulkAcknowledge,
  useAdvanceSurgeScan,
  useNewFilmMonitor,
  type SurgeDetection,
  type AdvanceSurgeScanResponse,
  type NewFilmSurge,
  type NewFilmSurgeResponse,
} from './usePriceAlerts';

// Scrapes
export {
  useScrapeSources,
  useScrapeSource,
  useCreateScrapeSource,
  useUpdateScrapeSource,
  useDeleteScrapeSource,
  useScrapeJobs,
  useScrapeJobStatus,
  useScrapeJobData,
  useTriggerScrape,
  useScrapeStatus,
  useCancelScrape,
  useFetchShowtimes,
  useEstimateScrapeTime,
  useSearchTheatersFandango,
  useSearchTheatersCache,
  useLiveScrapeJobs,
  type Showing,
  type TheaterSearchResult,
} from './useScrapes';

// Users
export {
  useUsers,
  useUser,
  useCreateUser,
  useUpdateUser,
  useDeleteUser,
  useChangePassword,
  useResetPassword,
} from './useUsers';

// Markets
export { useMarkets, useMarketTheaters, useMarketsHierarchy } from './useMarkets';

// Theaters
export {
  useTheaters,
  useTheaterFilms,
  usePriceHistory,
  type PriceHistoryEntry,
} from './useTheaters';

// Markets (additional exports)
export { useTheaterCache } from './useMarkets';

// Circuit Benchmarks
export {
  useCircuitBenchmarks,
  useCircuitBenchmarkWeeks,
  useWeekBenchmarks,
  useCircuitComparison,
  useSyncCircuitBenchmarks,
} from './useCircuitBenchmarks';

// Presales
export {
  usePresales,
  usePresaleFilms,
  usePresaleTrajectory,
  usePresaleVelocity,
  usePresaleComparison,
  useSyncPresales,
} from './usePresales';

// Cache Management
export {
  useCacheStatus,
  useCacheMarkets,
  useCacheBackups,
  useRefreshCache,
  useUnmatchedTheaters,
  useMatchTheater,
} from './useCache';

// Reports
export {
  useOperatingHours,
  useDailyLineup,
  usePlfFormats,
  useGenerateShowtimeHtml,
  useGenerateShowtimePdf,
  useGenerateSelectionAnalysis,
  useFetchOperatingHours,
  type OperatingHoursScrapeRecord,
  type WeekComparisonRecord,
  type OperatingHoursScrapeResponse,
} from './useReports';

// System Health
export {
  useBasicHealth,
  useSystemHealth,
  getStatusColor,
  getStatusVariant,
  systemHealthKeys,
  type SystemHealthResponse,
  type ComponentHealth,
  type CircuitBreakerStatus,
} from './useSystemHealth';

// Schedule Alerts
export {
  useScheduleAlerts,
  usePendingScheduleAlerts,
  useScheduleAlertSummary,
  useAcknowledgeScheduleAlert,
  useBulkAcknowledgeScheduleAlerts,
  useScheduleMonitorConfig,
  useUpdateScheduleMonitorConfig,
  useScheduleMonitorStatus,
  useTriggerScheduleCheck,
  getAlertTypeInfo,
  scheduleAlertKeys,
  type ScheduleAlert,
  type ScheduleAlertSummary,
  type ScheduleMonitorConfig,
  type ScheduleMonitorStatus,
} from './useScheduleAlerts';

// Repair Queue
export {
  useRepairQueueStatus,
  useRepairQueueJobs,
  useRepairQueueFailed,
  useResetRepairJob,
  useClearFailedJobs,
  useProcessRepairQueue,
  useMaintenanceHistory,
  useRunMaintenance,
  getTimeUntilRetry,
  getBackoffDisplay,
  repairQueueKeys,
  type RepairJob,
  type RepairQueueStatus,
  type MaintenanceRun,
  type MaintenanceHistoryEntry,
} from './useRepairQueue';

// Market Context / Theater Config
export {
  useTheaterOperatingHours,
  useUpdateTheaterOperatingHours,
} from './useOperatingHoursConfig';

// Films
export {
  useFilms,
  useEnrichFilm,
  useDiscoverFandango,
} from './useFilms';

// Audit Logs
export {
  useAuditLogs,
  useAuditLogEventTypes,
  useAuditLogCategories,
  getSeverityStyle,
  type AuditLogEntry,
} from './useAuditLog';

// Sync
export {
  useEntTelligenceStatus,
  useSyncPrices,
  useSyncMarkets,
  useTaskStatus,
  type SyncStatus,
  type SyncResponse,
  type TaskStatusResponse,
} from './useSync';

// Baselines
export {
  useBaselines,
  useCreateBaseline,
  useUpdateBaseline,
  useDeleteBaseline,
  useBaselineCoverage,
  useFandangoDiscover,
  useFandangoAnalyze,
  useFandangoRefresh,
  useDiscoverFandangoBaselinesForTheaters,
  useEntTelligenceDiscover,
  useEntTelligenceAnalyze,
  useEntTelligenceRefresh,
  useEntTelligenceCircuits,
  useCircuitBaselines,
  usePremiumFormats,
  useSaveDiscoveredBaselines,
  useEventCinemaAnalysis,
  useEventCinemaKeywords,
  // Baseline Browser
  useBaselineMarkets,
  useMarketDetail,
  useTheaterBaselines,
  // Baseline Maintenance
  useDeduplicateBaselines,
  type DeduplicateResponse,
  // Data Source Comparison
  useCompareDataSources,
  type PriceComparisonItem,
  type PriceComparisonResponse,
  type SavedBaseline,
  type DiscoveredBaseline,
  type DiscoveryResponse,
  type CircuitAnalysis,
  type FormatBreakdown,
  type PriceAnalysis,
  type CircuitInfo,
  type CreateBaselineRequest,
  type BaselineCoverage,
  type EventFilmPricing,
  type EventCinemaVariation,
  type EventCinemaAnalysis,
  // Baseline Browser types
  type MarketSummary,
  type TheaterSummary,
  type CircuitSummary,
  type MarketDetail,
  type TheaterBaseline,
  type TheaterBaselinesResponse,
} from './useBaselines';

// Market Baselines (Fandango scraping)
export {
  useMarketStats,
  useMarketScrapePlan,
  useTriggerMarketScrape,
  useMarketScrapeStatus,
  useCancelMarketScrape,
  marketBaselineKeys,
  type MarketStats,
  type MarketScrapePlan,
  type MarketScrapeRequest,
  type MarketScrapeJob,
  type MarketScrapeStartResponse,
} from './useMarketBaselines';

// Market Context / Heatmap
export {
  useTheaterMetadata,
  useMarketEvents,
  useSyncMarketContext,
  useHeatmapData,
  type TheaterMetadata,
  type MarketEvent,
  type SyncResult,
  type HeatmapTheaterData,
  type HeatmapDataResponse,
} from './useMarketContext';

// Company Profiles
export {
  useCompanyProfiles,
  useCompanyProfile,
  useDiscoverProfile,
  useDiscoverAllProfiles,
  useDeleteProfile,
  useCleanupDuplicateProfiles,
  useDiscountDayDiagnostic,
  useDataCoverage,
  getDayName,
  formatConfidence,
  getConfidenceLevel,
  getCoverageAssessmentColor,
  type CompanyProfile,
  type DiscountDayInfo,
  type ProfileListResponse,
  type DiscoverRequest,
  type DiscoverResponse,
  type DayPriceAnalysis,
  type DiscountDayDiagnostic,
  type DayCoverage,
  type DataCoverageResponse,
} from './useCompanyProfiles';

// Coverage Gaps
export {
  useTheaterCoverage,
  useAllTheaterCoverage,
  useCoverageHierarchy,
  useMarketCoverage,
  getCoverageLevel,
  getSeverityColor,
  getCoverageColor,
  formatDaysMissing,
  type GapInfo,
  type BaselineInfo,
  type CoverageReport,
  type TheaterCoverageSummary,
  type CoverageListResponse,
  type CoverageHierarchy,
  type CompanyCoverage,
  type DirectorCoverage,
  type MarketCoverage,
  type MarketCoverageDetail,
  type TheaterCoverageDetail,
} from './useCoverageGaps';

// Theater Onboarding
export {
  useOnboardingStatus,
  usePendingTheaters,
  useTheatersByMarket,
  useCoverageIndicators,
  useStartOnboarding,
  useBulkStartOnboarding,
  useRecordScrape,
  useDiscoverBaselines,
  useLinkProfile,
  useConfirmBaselines,
  // Amenity discovery hooks
  useTheatersMissingAmenities,
  useDiscoverAmenities,
  useBackfillAmenities,
  type OnboardingStatus,
  type OnboardingSteps,
  type OnboardingStep,
  type OnboardingCoverage,
  type PendingTheater,
  type CoverageIndicators,
  type DiscoveryResult,
  type StartOnboardingRequest,
  type BulkStartRequest,
  type RecordScrapeRequest,
  type DiscoverBaselinesRequest,
  type LinkProfileRequest,
  type ConfirmBaselinesRequest,
  // Amenity types
  type TheaterMissingAmenities,
  type AmenityDiscoveryResult as OnboardingAmenityResult,
  type BackfillAmenitiesRequest,
  type BackfillResult,
} from './useOnboarding';

// Discount Programs (Circuit-Level)
export {
  useDiscountPrograms,
  useCreateDiscountProgram,
  useDeleteDiscountProgram,
  useProfileGaps,
  useResolveGap,
  useProfileVersions,
  type DiscountProgram,
  type CreateDiscountProgramRequest,
  type ProfileGap,
  type ResolveGapRequest,
} from './useDiscountPrograms';

// Alternative Content (Special Events)
export {
  useACFilms,
  useACFilm,
  useCreateACFilm,
  useUpdateACFilm,
  useDeleteACFilm,
  useRunACDetection,
  useACDetectionPreview,
  useCheckFilm,
  useCircuitACPricing,
  useCircuitACPricingByName,
  useUpdateCircuitACPricing,
  useACFilmTitlesSet,
  isAlternativeContent,
  getContentTypeLabel,
  getContentTypeColor,
  CONTENT_TYPE_LABELS,
  CONTENT_TYPE_COLORS,
  type ACFilm,
  type ACFilmListResponse,
  type CreateACFilmRequest,
  type UpdateACFilmRequest,
  type DetectionResult,
  type DetectionPreview,
  type FilmCheckResult,
  type CircuitACPricing,
  type UpdateCircuitACPricingRequest,
} from './useAlternativeContent';

// Theater Amenities (Discovery & Management)
export {
  useTheaterAmenities,
  useTheaterAmenity,
  useAmenitiesSummary,
  useCreateTheaterAmenities,
  useUpdateTheaterAmenities,
  useDeleteTheaterAmenities,
  useDiscoverTheaterAmenities,
  useDiscoverAllTheaterAmenities,
  useFormatSummary,
  useScreenCountEstimate,
  theaterAmenitiesKeys,
  getFormatCategoryLabel,
  getPremiumFormatCount,
  getAmenityScoreColor,
  FORMAT_CATEGORY_LABELS,
  type TheaterAmenities,
  type TheaterAmenitiesRequest,
  type AmenitySummary,
  type DiscoveryRequest as AmenityDiscoveryRequest,
  type DiscoveryResult as AmenityDiscoveryResult,
  type DiscoverAllResponse,
  type FormatSummary,
  type ScreenCountEstimate,
  type AmenitiesFilters,
} from './useTheaterAmenities';
