import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

// Mock react-leaflet to avoid ESM/CJS issues
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => null,
  Popup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CircleMarker: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// Mock leaflet css
vi.mock('leaflet/dist/leaflet.css', () => ({}));

import { App } from './App';

describe('App', () => {
  it('renders without crashing', () => {
    // App has its own BrowserRouter, so no need to wrap
    render(<App />);
    // App should render without throwing
    expect(document.body).toBeTruthy();
  });
});
