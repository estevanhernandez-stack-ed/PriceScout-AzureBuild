import { Outlet, Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

export function AuthLayout() {
  const { isAuthenticated } = useAuthStore();

  // If already authenticated, redirect to dashboard
  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
      {/* PriceScout Logo */}
      <div className="mb-8">
        <img
          src="/PriceScoutLogo.png"
          alt="PriceScout"
          className="h-40 w-auto"
        />
      </div>
      <div className="w-full max-w-md">
        <Outlet />
      </div>
      {/* Footer */}
      <div className="mt-8 text-sm text-muted-foreground">
        Developed @ 626Labs LLC
      </div>
    </div>
  );
}
