import { Outlet, Link, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Users,
  LogOut,
  Menu,
  MapPin,
  Clock,
  Crosshair,
  Calendar,
  BarChart3,
  Ticket,
  History,
  Image,
  HardDrive,
  Link2,
  Moon,
  Sun,
  Rocket,
  Trash2,
  Bug,
  Bell,
  Activity,
  Wrench,
  FileDown,
  GraduationCap,
  Sparkles,
  Target,
  Map,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { TrainingCenter } from '@/components/training/TrainingCenter';

const scrapingModes = [
  { name: 'Market Mode', href: '/market-mode', icon: MapPin },
  { name: 'Operating Hours Mode', href: '/operating-hours', icon: Clock },
  { name: 'CompSnipe Mode', href: '/compsnipe', icon: Crosshair },
  { name: 'Daily Lineup', href: '/daily-lineup', icon: Calendar },
];

const analyticsAndData = [
  { name: 'Historical Data and Analysis', href: '/historical-data', icon: History },
  { name: 'Circuit Benchmarks', href: '/circuit-benchmarks', icon: BarChart3 },
  { name: 'Presale Tracking', href: '/presale-tracking', icon: Ticket },
  { name: 'Price Baselines', href: '/baselines', icon: Target },
  { name: 'Price Heatmap', href: '/analytics/heatmap', icon: Map },
  { name: 'Poster Board', href: '/poster-board', icon: Image },
  { name: 'Schedule Alerts', href: '/schedule-alerts', icon: Bell },
  { name: 'Export Center', href: '/export-center', icon: FileDown },
];

const adminNavigation = [
  { name: 'Data Management', href: '/admin/data-management', icon: HardDrive },
  { name: 'Theater Matching', href: '/admin/theater-matching', icon: Link2 },
  { name: 'System Health', href: '/admin/system-health', icon: Activity },
  { name: 'Repair Queue', href: '/admin/repair-queue', icon: Wrench },
  { name: 'Audit Log', href: '/admin/audit-log', icon: History },
  { name: 'Admin', href: '/admin/users', icon: Users },
];

export function MainLayout() {
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(true);
  const [selectedCompany, setSelectedCompany] = useState(user?.company || 'Marcus Theatres');
  const [captureHtmlOnFailure, setCaptureHtmlOnFailure] = useState(false);
  const [captureHtmlSnapshots, setCaptureHtmlSnapshots] = useState(false);
  const [trainingOpen, setTrainingOpen] = useState(false);

  const isAdmin = user?.role === 'admin';
  const isManager = user?.role === 'manager';
  const isOperator = user?.role === 'operator';
  const isAuditor = user?.role === 'auditor';

  // Any role that can see some level of admin tools
  const hasAdminAccess = isAdmin || isManager || isOperator || isAuditor;

  // Filter admin navigation based on roles
  const filteredAdminNav = adminNavigation.filter(item => {
    if (isAdmin) return true;
    if (item.href === '/admin/system-health') return isOperator || isAuditor || isManager;
    if (item.href === '/admin/data-management') return isOperator || isManager;
    if (item.href === '/admin/repair-queue') return isOperator || isManager;
    if (item.href === '/admin/users') return isAuditor || isManager;
    return false;
  });

  // Handle dark mode toggle
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  // Mock companies for demo - in production, fetch from API
  const companies = ['Marcus Theatres', 'AMC Entertainment', 'Regal Cinemas'];

  return (
    <div className="flex h-screen bg-background">
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-64 transform bg-card border-r transition-transform lg:static lg:translate-x-0 flex flex-col',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Dark Mode Toggle */}
        <div className="px-4 py-3 border-b">
          <button
            onClick={() => setDarkMode(!darkMode)}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
          >
            <span className={cn(
              'w-3 h-3 rounded-full',
              darkMode ? 'bg-primary' : 'bg-muted-foreground'
            )} />
            {darkMode ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            <span>Dark Mode</span>
          </button>
        </div>

        {/* Company Selection (Admin and Manager only) */}
        {(isAdmin || isManager) && (
          <div className="px-4 py-3 border-b">
            <p className="text-xs text-muted-foreground mb-2">Company Selection</p>
            <p className="text-xs text-primary mb-1">Select Company</p>
            <Select value={selectedCompany} onValueChange={setSelectedCompany}>
              <SelectTrigger className="w-full bg-secondary">
                <SelectValue placeholder="Select company" />
              </SelectTrigger>
              <SelectContent>
                {companies.map((company) => (
                  <SelectItem key={company} value={company}>
                    {company}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {/* User Info Card */}
        <div className="px-4 py-3 border-b bg-primary/10">
          <p className="text-sm">
            <span className="text-muted-foreground">User: </span>
            <span className="font-medium capitalize">{user?.username || 'admin'} ({user?.role})</span>
          </p>
          <p className="text-sm">
            <span className="text-muted-foreground">Company: </span>
            <span className="text-primary font-medium">{selectedCompany}</span>
          </p>
          <Button
            variant="outline"
            size="sm"
            className="w-full mt-2"
            onClick={logout}
          >
            <LogOut className="h-4 w-4 mr-2" />
            Logout
          </Button>
        </div>

        {/* Controls Section */}
        <div className="px-4 py-3 border-b">
          <p className="text-sm font-semibold mb-3">Controls</p>

          {/* Logo */}
          <div className="flex justify-center mb-3 bg-white rounded-lg p-2">
            <img
              src="/PriceScoutLogo.png"
              alt="PriceScout"
              className="h-24 w-auto"
            />
          </div>

          {/* Start New Report Button - Allowed for Admin, Manager, Operator */}
          {(isAdmin || isManager || isOperator) && (
            <Button
              variant="secondary"
              size="sm"
              className="w-full"
            >
              <Rocket className="h-4 w-4 mr-2" />
              Start New Report / Abort
            </Button>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 overflow-y-auto">
          {/* Dashboard Link */}
          <Link
            to="/dashboard"
            className="block mb-4"
            onClick={() => setSidebarOpen(false)}
          >
            <Button
              variant={location.pathname === '/dashboard' ? 'toggleActive' : 'toggle'}
              size="sm"
              className="w-full justify-start font-bold uppercase tracking-wider"
            >
              <Activity className="mr-2 h-4 w-4" />
              Dashboard
            </Button>
          </Link>

          {/* Select Mode */}
          <p className="px-3 pb-2 text-sm font-semibold opacity-60 uppercase tracking-tighter">Select Mode</p>

          {/* Scraping Modes */}
          {scrapingModes.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <Link
                key={item.name}
                to={item.href}
                className="block mb-1"
                onClick={() => setSidebarOpen(false)}
              >
                <Button
                  variant={isActive ? 'toggleActive' : 'toggle'}
                  size="sm"
                  className="w-full justify-start"
                >
                  {item.name}
                </Button>
              </Link>
            );
          })}

          {/* Analytics & Data */}
          {analyticsAndData.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <Link
                key={item.name}
                to={item.href}
                className="block mb-1"
                onClick={() => setSidebarOpen(false)}
              >
                <Button
                  variant={isActive ? 'toggleActive' : 'toggle'}
                  size="sm"
                  className="w-full justify-start"
                >
                  {item.name}
                </Button>
              </Link>
            );
          })}

          {/* Admin Navigation */}
          {hasAdminAccess && (
            <>
              <div className="border-t my-2 pt-2 px-3">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Management</p>
              </div>
              {filteredAdminNav.map((item) => {
                const isActive = location.pathname === item.href;
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    className="block mb-1"
                    onClick={() => setSidebarOpen(false)}
                  >
                    <Button
                      variant={isActive ? 'toggleActive' : 'toggle'}
                      size="sm"
                      className="w-full justify-start"
                    >
                      <item.icon className="mr-2 h-4 w-4" />
                      {item.name}
                    </Button>
                  </Link>
                );
              })}
            </>
          )}

          {/* Help & Training section */}
          <div className="border-t my-2 pt-2 px-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Help & Training</p>
            <Button
              variant="toggle"
              size="sm"
              className="w-full justify-start text-primary font-medium hover:bg-primary/10"
              onClick={() => setTrainingOpen(true)}
            >
              <GraduationCap className="mr-2 h-4 w-4" />
              Training Center
            </Button>
            <Button
              variant="toggle"
              size="sm"
              className="w-full justify-start mt-1"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              What's New?
            </Button>
          </div>
        </nav>

        {/* Developer Tools (Admin only) */}
        {isAdmin && (
          <div className="px-4 py-3 border-t">
            <p className="text-sm font-semibold mb-3">Developer Tools</p>

            {/* Toggle switches */}
            <div className="space-y-2 mb-3">
              <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={captureHtmlOnFailure}
                  onChange={(e) => setCaptureHtmlOnFailure(e.target.checked)}
                  className="rounded border-border"
                />
                <span>Capture HTML on Failure</span>
                <span className="text-muted-foreground">ⓘ</span>
              </label>
              <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={captureHtmlSnapshots}
                  onChange={(e) => setCaptureHtmlSnapshots(e.target.checked)}
                  className="rounded border-border"
                />
                <span>Capture HTML Snapshots</span>
                <span className="text-muted-foreground">ⓘ</span>
              </label>
            </div>

            {/* Diagnostic Buttons */}
            <Button
              variant="secondary"
              size="sm"
              className="w-full mb-2"
            >
              <Bug className="h-4 w-4 mr-2" />
              Run Market Diagnostic
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete Theater Cache
            </Button>
          </div>
        )}

        {/* Footer */}
        <div className="px-4 py-3 border-t text-xs text-muted-foreground">
          <p>Cache last updated: 2026-01-09 00:50:46</p>
          <p className="mt-1">Developed @ 626Labs LLC</p>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-16 items-center gap-4 border-b bg-card px-6 lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-2 text-muted-foreground hover:bg-accent"
          >
            <Menu className="h-6 w-6" />
          </button>
          <span className="text-lg font-semibold">PriceScout</span>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      
      <TrainingCenter open={trainingOpen} onOpenChange={setTrainingOpen} user={user} />
    </div>
  );
}
