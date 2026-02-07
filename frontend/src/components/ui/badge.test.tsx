import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge, badgeVariants } from './badge';

describe('Badge component', () => {
  it('renders children correctly', () => {
    render(<Badge>Test Badge</Badge>);
    expect(screen.getByText('Test Badge')).toBeInTheDocument();
  });

  it('applies default variant styles', () => {
    render(<Badge data-testid="badge">Default</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('bg-primary');
  });

  it('applies secondary variant styles', () => {
    render(<Badge variant="secondary" data-testid="badge">Secondary</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('bg-secondary');
  });

  it('applies destructive variant styles', () => {
    render(<Badge variant="destructive" data-testid="badge">Destructive</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('bg-destructive');
  });

  it('applies outline variant styles', () => {
    render(<Badge variant="outline" data-testid="badge">Outline</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('text-foreground');
  });

  it('applies success variant styles', () => {
    render(<Badge variant="success" data-testid="badge">Success</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('bg-green-500/20');
  });

  it('applies warning variant styles', () => {
    render(<Badge variant="warning" data-testid="badge">Warning</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('bg-yellow-500/20');
  });

  it('applies info variant styles', () => {
    render(<Badge variant="info" data-testid="badge">Info</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('bg-blue-500/20');
  });

  it('applies custom className', () => {
    render(<Badge className="custom-class" data-testid="badge">Custom</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveClass('custom-class');
  });

  it('passes through additional props', () => {
    render(<Badge data-testid="badge" aria-label="status badge">Status</Badge>);
    const badge = screen.getByTestId('badge');
    expect(badge).toHaveAttribute('aria-label', 'status badge');
  });
});

describe('badgeVariants', () => {
  it('returns correct classes for default variant', () => {
    const classes = badgeVariants({ variant: 'default' });
    expect(classes).toContain('bg-primary');
  });

  it('returns correct classes for secondary variant', () => {
    const classes = badgeVariants({ variant: 'secondary' });
    expect(classes).toContain('bg-secondary');
  });

  it('uses default variant when none specified', () => {
    const classes = badgeVariants({});
    expect(classes).toContain('bg-primary');
  });
});
