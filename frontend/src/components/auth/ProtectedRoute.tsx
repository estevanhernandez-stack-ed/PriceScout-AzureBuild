import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: string | string[];
}

export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { isAuthenticated, user, isLoading } = useAuthStore();
  const location = useLocation();

  // Show loading while checking auth
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  // Not authenticated - redirect to login
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Check role requirement
  if (requiredRole && user) {
    const roles = Array.isArray(requiredRole) ? requiredRole : [requiredRole];
    
    // Check if user has any of the required roles
    // OR if user is admin (admin bypasses most checks)
    const hasRole = roles.includes(user.role) || user.role === 'admin';
    
    // Hierarchy fallback for basic roles (admin > manager > user)
    const roleHierarchy: Record<string, number> = { admin: 3, manager: 2, operator: 2, auditor: 1.5, user: 1 };
    const userLevel = roleHierarchy[user.role] || 0;
    
    // If it's a single string like 'manager', we might want hierarchy
    const isHigherOrEqual = typeof requiredRole === 'string' && userLevel >= (roleHierarchy[requiredRole] || 0);

    if (!hasRole && !isHigherOrEqual) {
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-4">
          <h1 className="text-2xl font-bold">Access Denied</h1>
          <p className="text-muted-foreground text-center">
            You don&apos;t have permission to access this page.<br />
            Required role: {roles.join(', ')} (Your role: {user.role})
          </p>
          <button 
            onClick={() => window.history.back()}
            className="text-primary hover:underline"
          >
            Go Back
          </button>
        </div>
      );
    }
  }

  return <>{children}</>;
}
