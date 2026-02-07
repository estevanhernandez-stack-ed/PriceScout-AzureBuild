import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button, buttonVariants } from './button';

describe('Button component', () => {
  it('renders children correctly', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument();
  });

  it('handles click events', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click me</Button>);

    fireEvent.click(screen.getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('applies default variant styles', () => {
    render(<Button data-testid="btn">Default</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('bg-primary');
  });

  it('applies secondary variant styles', () => {
    render(<Button variant="secondary" data-testid="btn">Secondary</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('bg-secondary');
  });

  it('applies destructive variant styles', () => {
    render(<Button variant="destructive" data-testid="btn">Destructive</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('bg-destructive');
  });

  it('applies outline variant styles', () => {
    render(<Button variant="outline" data-testid="btn">Outline</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('border');
    expect(button).toHaveClass('bg-background');
  });

  it('applies ghost variant styles', () => {
    render(<Button variant="ghost" data-testid="btn">Ghost</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('hover:bg-accent');
  });

  it('applies link variant styles', () => {
    render(<Button variant="link" data-testid="btn">Link</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('text-primary');
    expect(button).toHaveClass('underline-offset-4');
  });

  it('applies toggle variant styles', () => {
    render(<Button variant="toggle" data-testid="btn">Toggle</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('bg-secondary');
  });

  it('applies toggleActive variant styles', () => {
    render(<Button variant="toggleActive" data-testid="btn">Active</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('bg-primary');
    expect(button).toHaveClass('border-primary');
  });

  it('applies default size styles', () => {
    render(<Button data-testid="btn">Default Size</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('h-9');
    expect(button).toHaveClass('px-4');
  });

  it('applies small size styles', () => {
    render(<Button size="sm" data-testid="btn">Small</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('h-8');
    expect(button).toHaveClass('px-3');
  });

  it('applies large size styles', () => {
    render(<Button size="lg" data-testid="btn">Large</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('h-10');
    expect(button).toHaveClass('px-8');
  });

  it('applies icon size styles', () => {
    render(<Button size="icon" data-testid="btn">Icon</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('h-9');
    expect(button).toHaveClass('w-9');
  });

  it('is disabled when disabled prop is true', () => {
    render(<Button disabled>Disabled</Button>);
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
  });

  it('has correct opacity when disabled', () => {
    render(<Button disabled data-testid="btn">Disabled</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('disabled:opacity-50');
  });

  it('applies custom className', () => {
    render(<Button className="custom-class" data-testid="btn">Custom</Button>);
    const button = screen.getByTestId('btn');
    expect(button).toHaveClass('custom-class');
  });

  it('renders as child element when asChild is true', () => {
    render(
      <Button asChild>
        <a href="/test">Link Button</a>
      </Button>
    );
    const link = screen.getByRole('link', { name: 'Link Button' });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/test');
  });

  it('forwards ref correctly', () => {
    const ref = { current: null };
    render(<Button ref={ref}>Ref Button</Button>);
    expect(ref.current).toBeInstanceOf(HTMLButtonElement);
  });

  it('passes through type attribute', () => {
    render(<Button type="submit">Submit</Button>);
    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('type', 'submit');
  });
});

describe('buttonVariants', () => {
  it('returns correct classes for default variant and size', () => {
    const classes = buttonVariants({ variant: 'default', size: 'default' });
    expect(classes).toContain('bg-primary');
    expect(classes).toContain('h-9');
  });

  it('returns correct classes for secondary variant', () => {
    const classes = buttonVariants({ variant: 'secondary' });
    expect(classes).toContain('bg-secondary');
  });

  it('uses defaults when no options specified', () => {
    const classes = buttonVariants({});
    expect(classes).toContain('bg-primary');
    expect(classes).toContain('h-9');
  });
});
