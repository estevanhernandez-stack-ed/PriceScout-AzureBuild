import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  GraduationCap, 
  MousePointer2, 
  X, 
  ChevronRight, 
  ChevronLeft, 
  CheckCircle2,
  Sparkles,
  Zap,
  ShieldCheck,
  Activity,
  Database,
  LayoutDashboard,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface TrainingStep {
  title: string;
  description: string;
  target?: string;
  position?: 'top' | 'bottom' | 'left' | 'right';
  roles?: string[]; // Only show to these roles
}

const COMMON_STEPS: TrainingStep[] = [
  {
    title: "Welcome to PriceScout 2.0",
    description: "Our new React-based dashboard is designed for speed and reliability. This tour will adapt based on your assigned user role.",
  },
  {
    title: "Unified Navigation",
    description: "Switch between operational modes (Market, Operating Hours) and Analytics (Historical, Benchmarks) from this sidebar.",
    target: "nav.flex-1",
  }
];

const OPERATOR_STEPS: TrainingStep[] = [
  {
    title: "Background Sync Monitoring",
    description: "Syncing data from EntTelligence now runs in the background. You'll see real-time progress cards in the sidebar and top-right when a sync is active.",
    target: ".bg-primary/5",
  },
  {
    title: "Cache Management",
    description: "Update theater mappings and clear local caches directly from the Data Management page without needing a developer.",
    target: "a[href='/admin/data-management']",
  }
];

const DATA_OPS_STEPS: TrainingStep[] = [
  {
      title: "Market Context Analysis",
      description: "Deep dive into theater-specific market context and competitor influence scores.",
      target: "a[href='/market-mode']",
  },
  {
      title: "Theater Matching Engine",
      description: "Ensure your theaters are correctly mapped to competitor theaters for accurate price checks.",
      target: "a[href='/admin/theater-matching']",
  }
];

const SECURITY_STEPS: TrainingStep[] = [
  {
      title: "System Health & Panic Button",
      description: "Monitor API latency and circuit breaker status. Use the 'Force Open' button for emergency service isolation.",
      target: "a[href='/admin/system-health']",
  },
  {
      title: "Security & Governance Audit",
      description: "Every sensitive action is tracked. Use the Audit Log to review system changes and user access patterns.",
      target: "a[href='/admin/audit-log']",
  }
];


export function TrainingCenter({ 
  open, 
  onOpenChange, 
  user 
}: { 
  open: boolean, 
  onOpenChange: (open: boolean) => void,
  user: any
}) {
  const [activeTour, setActiveTour] = useState(false);
  const [activeAutomated, setActiveAutomated] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(0);
  const navigate = useNavigate();

  const isAdmin = user?.role === 'admin';
  const isOperator = user?.role === 'operator' || user?.role === 'manager';

  const steps = [
    ...COMMON_STEPS,
    ...(isOperator ? OPERATOR_STEPS : []),
    ...(isAdmin ? [...DATA_OPS_STEPS, ...SECURITY_STEPS] : [])
  ];

  // Automated Fly-By Timer Logic
  useEffect(() => {
    let interval: NodeJS.Timeout;
    let stepTimer: NodeJS.Timeout;

    if (activeAutomated) {
      setProgress(0);
      
      // Progress bar interval
      interval = setInterval(() => {
        setProgress(prev => {
          if (prev >= 100) return 0;
          return prev + 1;
        });
      }, 30); // 3 seconds per step (30 * 100 = 3000ms)

      // Step advance interval
      stepTimer = setInterval(() => {
        setCurrentStep(prev => {
          if (prev >= steps.length - 1) {
            setActiveAutomated(false);
            return 0;
          }
          return prev + 1;
        });
      }, 3000);
    }

    return () => {
      clearInterval(interval);
      clearInterval(stepTimer);
    };
  }, [activeAutomated, steps.length]);

  // Sync navigation for Automated Fly-By
  useEffect(() => {
    if (activeAutomated && steps[currentStep]?.target && steps[currentStep].target.startsWith('a[href')) {
        const href = steps[currentStep].target.match(/'(.*?)'/)?.[1];
        if (href && window.location.pathname !== href) {
            navigate(href);
        }
    }
  }, [activeAutomated, currentStep, steps, navigate]);

  const handleStartTour = () => {
    onOpenChange(false);
    setActiveTour(true);
    setCurrentStep(0);
  };

  const handleNextStep = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(prev => prev + 1);
    } else {
      setActiveTour(false);
    }
  };

  const handlePrevStep = () => {
    if (currentStep > 0) {
      setCurrentStep(prev => prev - 1);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[600px] bg-card border-primary/20">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-2xl font-bold">
              <GraduationCap className="h-6 w-6 text-primary" />
              PriceScout Training Center
            </DialogTitle>
            <DialogDescription>
              Personalized training for your <strong>{user?.role}</strong> access level.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
            {/* Contextual Track Label */}
            <div className="md:col-span-2 flex items-center gap-2 mb-2">
              <div className="h-px flex-1 bg-border" />
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Standard Tracks</span>
              <div className="h-px flex-1 bg-border" />
            </div>
            {/* Interactive Module */}
            <div className="group relative p-6 rounded-xl border bg-secondary/30 hover:bg-secondary/50 transition-all cursor-pointer overflow-hidden border-primary/10 hover:border-primary/40" onClick={handleStartTour}>
              <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                <MousePointer2 className="h-24 w-24 text-primary" />
              </div>
              <Zap className="h-8 w-8 text-primary mb-4" />
              <h3 className="text-xl font-bold mb-2">Interactive Tour</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Walk through the interface with live guidance. Perfect for hands-on learners.
              </p>
              <div className="flex items-center text-primary font-semibold text-sm">
                Start Now <ChevronRight className="h-4 w-4 ml-1" />
              </div>
            </div>

            {/* Fly-By Module */}
            <div className="group relative p-6 rounded-xl border bg-secondary/30 hover:bg-secondary/50 transition-all cursor-pointer overflow-hidden border-primary/10 hover:border-primary/40" onClick={() => { onOpenChange(false); setActiveAutomated(true); setCurrentStep(0); }}>
              <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                <Zap className="h-24 w-24 text-primary" />
              </div>
              <Activity className="h-8 w-8 text-primary mb-4" />
              <h3 className="text-xl font-bold mb-2">Fly-By Walkthrough</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Watch the system navigate itself in real-time. Hands-free exploration.
              </p>
              <div className="flex items-center text-primary font-semibold text-sm">
                Begin Automated Tour <ChevronRight className="h-4 w-4 ml-1" />
              </div>
            </div>
          </div>

          {(isOperator || isAdmin) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
              <div className="md:col-span-2 flex items-center gap-2 mb-2 mt-2">
                <div className="h-px flex-1 bg-border" />
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Advanced Tracks</span>
                <div className="h-px flex-1 bg-border" />
              </div>

              {/* Data Ops Track */}
              <div 
                className={cn(
                  "group p-4 rounded-lg border transition-all",
                  isAdmin ? "bg-blue-500/5 border-blue-500/20 hover:bg-blue-500/10 cursor-pointer" : "opacity-50 grayscale cursor-not-allowed"
                )}
                onClick={() => { if (isAdmin) { onOpenChange(false); setActiveTour(true); setCurrentStep(COMMON_STEPS.length + (isOperator ? OPERATOR_STEPS.length : 0)); } }}
              >
                <div className="flex items-center gap-3 mb-2">
                  <Database className="h-5 w-5 text-blue-500" />
                  <h4 className="font-bold text-sm">Data Ops Mastery</h4>
                </div>
                <p className="text-[11px] text-muted-foreground">Master theater matching and data context analysis.</p>
              </div>

              {/* Security Track */}
              <div 
                className={cn(
                  "group p-4 rounded-lg border transition-all",
                  isAdmin ? "bg-purple-500/5 border-purple-500/20 hover:bg-purple-500/10 cursor-pointer" : "opacity-50 grayscale cursor-not-allowed"
                )}
                onClick={() => { if (isAdmin) { onOpenChange(false); setActiveTour(true); setCurrentStep(COMMON_STEPS.length + (isOperator ? OPERATOR_STEPS.length : 0) + DATA_OPS_STEPS.length); } }}
              >
                <div className="flex items-center gap-3 mb-2">
                  <ShieldCheck className="h-5 w-5 text-purple-500" />
                  <h4 className="font-bold text-sm">Security & Governance</h4>
                </div>
                <p className="text-[11px] text-muted-foreground">Advanced audit log analysis and system health monitoring.</p>
              </div>
            </div>
          )}

          <div className="mt-6 p-4 rounded-lg bg-primary/5 border border-primary/10">
            <h4 className="flex items-center gap-2 text-sm font-semibold mb-2">
              <Sparkles className="h-4 w-4 text-primary" />
              New in React Dashboard
            </h4>
            <ul className="text-xs text-muted-foreground space-y-2">
                <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-3 w-3 text-green-500" />
                    Asynchronous Celery Task support for large syncs
                </li>
                <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-3 w-3 text-green-500" />
                    Real-time alert notifications via WebSockets
                </li>
                <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-3 w-3 text-green-500" />
                    Advanced fuzzy matching for competitor theaters
                </li>
            </ul>
          </div>
        </DialogContent>
      </Dialog>

      {/* Automated Tour Overlay */}
      {activeAutomated && (
        <div className="fixed bottom-8 right-8 z-[100] w-full max-w-sm bg-card border-t-4 border-primary shadow-2xl rounded-xl p-6 animate-in slide-in-from-bottom-4 duration-300">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-bold uppercase tracking-wider">
              <Activity className="h-3 w-3 animate-pulse" /> Automated Fly-By: {currentStep + 1} / {steps.length}
            </div>
            <Button variant="ghost" size="icon" className="-mr-2 -mt-2" onClick={() => setActiveAutomated(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
               <Zap className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h3 className="text-lg font-bold mb-1">{steps[currentStep].title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                {steps[currentStep].description}
              </p>
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-3">
            <div className="flex items-center justify-between text-[10px] text-muted-foreground uppercase font-bold tracking-widest">
                <span>Next Action in 3s</span>
                <span>{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} className="h-1" />
            <div className="flex justify-between mt-2">
                <Button variant="outline" size="sm" className="h-7 text-[10px] items-center px-2" onClick={() => setActiveAutomated(false)}>
                    Stop Walkthrough
                </Button>
                <div className="text-[10px] text-primary italic font-medium">
                    Performing Action...
                </div>
            </div>
          </div>
          
          {steps[currentStep].target && (
            <div className="absolute -top-4 -left-4 w-8 h-8 rounded-full border-2 border-primary animate-ping opacity-75" />
          )}
        </div>
      )}

      {/* Interactive Tour Overlay */}
      {activeTour && (
        <div className="fixed inset-0 z-[100] bg-black/40 backdrop-blur-sm flex items-center justify-center p-6">
          <div className="w-full max-w-sm bg-card border-t-4 border-primary shadow-2xl rounded-xl p-6 relative animate-in fade-in zoom-in duration-300">
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-bold uppercase tracking-wider">
                <Zap className="h-3 w-3" /> Step {currentStep + 1} of {steps.length}
              </div>
              <Button variant="ghost" size="icon" className="-mr-2 -mt-2" onClick={() => setActiveTour(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
                {currentStep < COMMON_STEPS.length ? <LayoutDashboard className="h-5 w-5 text-primary" /> : 
                 currentStep < COMMON_STEPS.length + OPERATOR_STEPS.length ? <Activity className="h-5 w-5 text-primary" /> : 
                 <ShieldCheck className="h-5 w-5 text-primary" />}
              </div>
              <div>
                <h3 className="text-lg font-bold mb-1">{steps[currentStep].title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {steps[currentStep].description}
                </p>
              </div>
            </div>

            <div className="mt-8 flex items-center justify-between gap-3">
              <div className="flex gap-1">
                {steps.map((_, i) => (
                  <div 
                    key={i} 
                    className={cn(
                        "h-1 rounded-full transition-all",
                        i === currentStep ? "w-6 bg-primary" : "w-2 bg-muted"
                    )} 
                  />
                ))}
              </div>
              <div className="flex gap-2">
                {currentStep > 0 && (
                  <Button variant="outline" size="sm" onClick={handlePrevStep}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                )}
                <Button size="sm" onClick={handleNextStep}>
                  {currentStep === steps.length - 1 ? 'Finish' : 'Next'} 
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            </div>
            
            {/* Visual Indicator for Target (if we had specific coordinates) */}
            {steps[currentStep].target && (
                <div className="mt-6 pt-4 border-t border-primary/10">
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-mono italic">
                        <MousePointer2 className="h-3 w-3" />
                        Target element active in background
                    </div>
                </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
