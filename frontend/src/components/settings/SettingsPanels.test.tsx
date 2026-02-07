import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { MarketScopePanel } from './MarketScopePanel';
import { NameMappingPanel } from './NameMappingPanel';
import { SystemDiagnosticsPanel } from './SystemDiagnosticsPanel';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>{children}</BrowserRouter>
      </QueryClientProvider>
    );
  };
}

describe('MarketScopePanel', () => {
  it('renders loading state then data', async () => {
    render(<MarketScopePanel />, { wrapper: createWrapper() });

    // Should show loading initially
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('Total Theaters')).toBeInTheDocument();
    });

    expect(screen.getByText('204')).toBeInTheDocument();
    expect(screen.getAllByText('Markets').length).toBeGreaterThan(0);
    expect(screen.getByText('Per-Director Breakdown')).toBeInTheDocument();
  });

  it('shows unmatched theaters section', async () => {
    render(<MarketScopePanel />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText(/Unmatched Theaters/)).toBeInTheDocument();
    });

    expect(screen.getByText('Theater A')).toBeInTheDocument();
    expect(screen.getByText('Theater B')).toBeInTheDocument();
  });
});

describe('NameMappingPanel', () => {
  it('renders loading state then data', async () => {
    render(<NameMappingPanel />, { wrapper: createWrapper() });

    expect(document.querySelector('.animate-spin')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Theater Name Resolution Summary')).toBeInTheDocument();
    });

    expect(screen.getByText('Total Market Theaters')).toBeInTheDocument();
    expect(screen.getByText('Metadata Matched')).toBeInTheDocument();
    expect(screen.getByText('EntTelligence Matched')).toBeInTheDocument();
  });

  it('shows non-trivial matches with method badges', async () => {
    render(<NameMappingPanel />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText(/Non-Trivial Matches/)).toBeInTheDocument();
    });

    expect(screen.getByText('Marcus Cinema')).toBeInTheDocument();
    expect(screen.getByText('Marcus Cinemas')).toBeInTheDocument();
    expect(screen.getByText('normalized')).toBeInTheDocument();
  });

  it('shows known aliases', async () => {
    render(<NameMappingPanel />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText(/Known Aliases/)).toBeInTheDocument();
    });

    expect(screen.getByText('Movie Tavern Northlake')).toBeInTheDocument();
    expect(screen.getByText('Movie Tavern Tucker')).toBeInTheDocument();
  });
});

describe('SystemDiagnosticsPanel', () => {
  it('renders loading state then data', async () => {
    render(<SystemDiagnosticsPanel />, { wrapper: createWrapper() });

    expect(document.querySelector('.animate-spin')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Table Row Counts')).toBeInTheDocument();
    });

    expect(screen.getAllByText('EntTelligence').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Fandango').length).toBeGreaterThan(0);
    expect(screen.getByText('Configuration Summary')).toBeInTheDocument();
  });

  it('shows data source details', async () => {
    render(<SystemDiagnosticsPanel />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByText('2026-01-01 to 2026-02-06').length).toBeGreaterThan(0);
    });
  });

  it('shows config summary badges', async () => {
    render(<SystemDiagnosticsPanel />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Configuration Summary')).toBeInTheDocument();
    });

    expect(screen.getByText('Tax Estimation')).toBeInTheDocument();
    expect(screen.getByText('7.5%')).toBeInTheDocument();
  });
});
