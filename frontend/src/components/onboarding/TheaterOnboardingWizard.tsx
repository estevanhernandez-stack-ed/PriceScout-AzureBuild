import * as React from 'react';
import { useState } from 'react';
import {
  CheckCircle2,
  MapPin,
  Database,
  Search,
  Link,
  CheckCheck,
  Loader2,
  AlertCircle,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useOnboardingStatus,
  useStartOnboarding,
  useRecordScrape,
  useDiscoverBaselines,
  useLinkProfile,
  useConfirmBaselines,
  type OnboardingStatus,
  type DiscoveryResult,
} from '@/hooks/api/useOnboarding';
import { CoverageIndicators } from './CoverageIndicators';

// =============================================================================
// TYPES
// =============================================================================

interface TheaterOnboardingWizardProps {
  theaterName?: string;
  market?: string;
  onComplete?: (status: OnboardingStatus) => void;
  onCancel?: () => void;
}

interface StepConfig {
  id: number;
  key: string;
  title: string;
  description: string;
  icon: React.ReactNode;
}

const STEPS: StepConfig[] = [
  {
    id: 1,
    key: 'market_added',
    title: 'Add to Market',
    description: 'Register the theater in a market',
    icon: <MapPin className="h-5 w-5" />,
  },
  {
    id: 2,
    key: 'initial_scrape',
    title: 'Collect Prices',
    description: 'Initial price data collection',
    icon: <Database className="h-5 w-5" />,
  },
  {
    id: 3,
    key: 'baseline_discovered',
    title: 'Discover Baselines',
    description: 'Analyze pricing patterns',
    icon: <Search className="h-5 w-5" />,
  },
  {
    id: 4,
    key: 'profile_linked',
    title: 'Link Profile',
    description: 'Connect to company profile',
    icon: <Link className="h-5 w-5" />,
  },
  {
    id: 5,
    key: 'baseline_confirmed',
    title: 'Confirm & Activate',
    description: 'Review and activate baselines',
    icon: <CheckCheck className="h-5 w-5" />,
  },
];

// =============================================================================
// STEP INDICATOR COMPONENT
// =============================================================================

interface StepIndicatorProps {
  steps: StepConfig[];
  currentStep: number;
  completedSteps: Record<string, boolean>;
}

function StepIndicator({ steps, currentStep, completedSteps }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-between mb-8">
      {steps.map((step, index) => {
        const isCompleted = completedSteps[step.key];
        const isCurrent = currentStep === step.id;
        const isUpcoming = currentStep < step.id;

        return (
          <React.Fragment key={step.id}>
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  'w-10 h-10 rounded-full flex items-center justify-center border-2 transition-colors',
                  isCompleted && 'bg-green-500 border-green-500 text-white',
                  isCurrent && !isCompleted && 'border-primary bg-primary/10 text-primary',
                  isUpcoming && 'border-muted-foreground/30 text-muted-foreground/30'
                )}
              >
                {isCompleted ? (
                  <CheckCircle2 className="h-5 w-5" />
                ) : (
                  step.icon
                )}
              </div>
              <span
                className={cn(
                  'mt-2 text-xs font-medium text-center max-w-[80px]',
                  isCompleted && 'text-green-500',
                  isCurrent && !isCompleted && 'text-primary',
                  isUpcoming && 'text-muted-foreground/50'
                )}
              >
                {step.title}
              </span>
            </div>
            {index < steps.length - 1 && (
              <div
                className={cn(
                  'flex-1 h-0.5 mx-2',
                  completedSteps[steps[index + 1].key] || currentStep > step.id
                    ? 'bg-green-500'
                    : 'bg-muted-foreground/30'
                )}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// =============================================================================
// STEP CONTENT COMPONENTS
// =============================================================================

interface Step1Props {
  theaterName: string;
  setTheaterName: (name: string) => void;
  market: string;
  setMarket: (market: string) => void;
  circuitName: string;
  setCircuitName: (circuit: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
}

function Step1Content({
  theaterName,
  setTheaterName,
  market,
  setMarket,
  circuitName,
  setCircuitName,
  onSubmit,
  isLoading,
}: Step1Props) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="theater-name">Theater Name</Label>
        <Input
          id="theater-name"
          placeholder="e.g., Marcus Majestic Cinema"
          value={theaterName}
          onChange={(e) => setTheaterName(e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="market">Market</Label>
        <Input
          id="market"
          placeholder="e.g., Milwaukee, Chicago"
          value={market}
          onChange={(e) => setMarket(e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="circuit">Circuit (Optional)</Label>
        <Select value={circuitName} onValueChange={setCircuitName}>
          <SelectTrigger>
            <SelectValue placeholder="Auto-detect from name" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">Auto-detect</SelectItem>
            <SelectItem value="Marcus">Marcus Theatres</SelectItem>
            <SelectItem value="AMC">AMC Theatres</SelectItem>
            <SelectItem value="Regal">Regal Cinemas</SelectItem>
            <SelectItem value="Cinemark">Cinemark</SelectItem>
            <SelectItem value="B&B Theatres">B&B Theatres</SelectItem>
            <SelectItem value="Alamo Drafthouse">Alamo Drafthouse</SelectItem>
            <SelectItem value="Harkins">Harkins Theatres</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button
        onClick={onSubmit}
        disabled={!theaterName || !market || isLoading}
        className="w-full mt-4"
      >
        {isLoading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Adding Theater...
          </>
        ) : (
          <>
            Add to Market
            <ChevronRight className="ml-2 h-4 w-4" />
          </>
        )}
      </Button>
    </div>
  );
}

interface Step2Props {
  theaterName: string;
  onSubmit: (source: 'fandango' | 'enttelligence', count: number) => void;
  isLoading: boolean;
}

function Step2Content({ theaterName, onSubmit, isLoading }: Step2Props) {
  const [source, setSource] = useState<'fandango' | 'enttelligence'>('enttelligence');
  const [count, setCount] = useState<string>('');

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Collect initial price data for <strong>{theaterName}</strong> from one of the available sources.
      </p>
      <div className="space-y-2">
        <Label>Data Source</Label>
        <Select value={source} onValueChange={(v) => setSource(v as 'fandango' | 'enttelligence')}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="enttelligence">EntTelligence (Recommended)</SelectItem>
            <SelectItem value="fandango">Fandango Scraper</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="count">Price Records Collected</Label>
        <Input
          id="count"
          type="number"
          placeholder="e.g., 150"
          value={count}
          onChange={(e) => setCount(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          Enter the number of price records collected from the initial scrape.
        </p>
      </div>
      <Button
        onClick={() => onSubmit(source, parseInt(count, 10))}
        disabled={!count || parseInt(count, 10) < 1 || isLoading}
        className="w-full mt-4"
      >
        {isLoading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Recording...
          </>
        ) : (
          <>
            Record Scrape Completion
            <ChevronRight className="ml-2 h-4 w-4" />
          </>
        )}
      </Button>
    </div>
  );
}

interface Step3Props {
  theaterName: string;
  discoveryResult: DiscoveryResult | null;
  onDiscover: (lookbackDays: number, minSamples: number) => void;
  isLoading: boolean;
}

function Step3Content({ theaterName, discoveryResult, onDiscover, isLoading }: Step3Props) {
  const [lookbackDays, setLookbackDays] = useState<number>(30);
  const [minSamples, setMinSamples] = useState<number>(5);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Analyze collected price data to discover baseline prices for <strong>{theaterName}</strong>.
      </p>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Lookback Period (days)</Label>
          <Input
            type="number"
            value={lookbackDays}
            onChange={(e) => setLookbackDays(parseInt(e.target.value, 10))}
            min={7}
            max={365}
          />
        </div>
        <div className="space-y-2">
          <Label>Min. Samples</Label>
          <Input
            type="number"
            value={minSamples}
            onChange={(e) => setMinSamples(parseInt(e.target.value, 10))}
            min={3}
            max={100}
          />
        </div>
      </div>

      {discoveryResult && (
        <Card className="bg-muted/50">
          <CardContent className="pt-4">
            {discoveryResult.success ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-green-500">
                  <CheckCircle2 className="h-5 w-5" />
                  <span className="font-medium">Discovery Complete</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>Baselines Created:</div>
                  <div className="font-medium">{discoveryResult.baselines_created}</div>
                  <div>Coverage Score:</div>
                  <div className="font-medium">{(discoveryResult.coverage_score * 100).toFixed(0)}%</div>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {discoveryResult.formats_discovered.map((f) => (
                    <Badge key={f} variant="secondary">{f}</Badge>
                  ))}
                  {discoveryResult.ticket_types_discovered.map((t) => (
                    <Badge key={t} variant="outline">{t}</Badge>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-yellow-500">
                <AlertCircle className="h-5 w-5" />
                <span>{discoveryResult.message || 'No baselines discovered'}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Button
        onClick={() => onDiscover(lookbackDays, minSamples)}
        disabled={isLoading}
        className="w-full"
      >
        {isLoading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Discovering Baselines...
          </>
        ) : discoveryResult?.success ? (
          <>
            Re-run Discovery
            <Search className="ml-2 h-4 w-4" />
          </>
        ) : (
          <>
            Discover Baselines
            <ChevronRight className="ml-2 h-4 w-4" />
          </>
        )}
      </Button>
    </div>
  );
}

interface Step4Props {
  theaterName: string;
  circuitName: string | null;
  onLink: (circuit?: string) => void;
  isLoading: boolean;
}

function Step4Content({ theaterName, circuitName, onLink, isLoading }: Step4Props) {
  const [selectedCircuit, setSelectedCircuit] = useState(circuitName || '');

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Link <strong>{theaterName}</strong> to a company profile for circuit-wide intelligence.
      </p>
      <div className="space-y-2">
        <Label>Circuit</Label>
        <Select value={selectedCircuit} onValueChange={setSelectedCircuit}>
          <SelectTrigger>
            <SelectValue placeholder={circuitName || 'Select circuit'} />
          </SelectTrigger>
          <SelectContent>
            {circuitName && (
              <SelectItem value={circuitName}>{circuitName} (Detected)</SelectItem>
            )}
            <SelectItem value="Marcus">Marcus Theatres</SelectItem>
            <SelectItem value="AMC">AMC Theatres</SelectItem>
            <SelectItem value="Regal">Regal Cinemas</SelectItem>
            <SelectItem value="Cinemark">Cinemark</SelectItem>
            <SelectItem value="B&B Theatres">B&B Theatres</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button
        onClick={() => onLink(selectedCircuit || undefined)}
        disabled={isLoading}
        className="w-full mt-4"
      >
        {isLoading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Linking Profile...
          </>
        ) : (
          <>
            Link to Profile
            <ChevronRight className="ml-2 h-4 w-4" />
          </>
        )}
      </Button>
    </div>
  );
}

interface Step5Props {
  theaterName: string;
  status: OnboardingStatus;
  onConfirm: (notes?: string) => void;
  isLoading: boolean;
}

function Step5Content({ theaterName, onConfirm, isLoading }: Omit<Step5Props, 'status'>) {
  const [notes, setNotes] = useState('');

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Review the discovered baselines and confirm to activate surge detection for{' '}
        <strong>{theaterName}</strong>.
      </p>

      <CoverageIndicators theaterName={theaterName} compact />

      <div className="space-y-2">
        <Label htmlFor="notes">Confirmation Notes (Optional)</Label>
        <Input
          id="notes"
          placeholder="Any notes about this theater's baselines..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      <Button
        onClick={() => onConfirm(notes || undefined)}
        disabled={isLoading}
        className="w-full mt-4"
        variant="default"
      >
        {isLoading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Confirming...
          </>
        ) : (
          <>
            <CheckCheck className="mr-2 h-4 w-4" />
            Confirm & Activate Baselines
          </>
        )}
      </Button>
    </div>
  );
}

// =============================================================================
// MAIN WIZARD COMPONENT
// =============================================================================

export function TheaterOnboardingWizard({
  theaterName: initialTheaterName = '',
  market: initialMarket = '',
  onComplete,
  onCancel,
}: TheaterOnboardingWizardProps) {
  // Form state
  const [theaterName, setTheaterName] = useState(initialTheaterName);
  const [market, setMarket] = useState(initialMarket);
  const [circuitName, setCircuitName] = useState('');
  const [discoveryResult, setDiscoveryResult] = useState<DiscoveryResult | null>(null);

  // Fetch existing status if theater name provided
  const { data: existingStatus } = useOnboardingStatus(theaterName, {
    enabled: !!theaterName && theaterName.length > 3,
  });

  // Mutations
  const startOnboarding = useStartOnboarding();
  const recordScrape = useRecordScrape();
  const discoverBaselines = useDiscoverBaselines();
  const linkProfile = useLinkProfile();
  const confirmBaselines = useConfirmBaselines();

  // Determine current status
  const status = existingStatus;
  const completedSteps = status
    ? {
        market_added: status.steps.market_added.completed,
        initial_scrape: status.steps.initial_scrape.completed,
        baseline_discovered: status.steps.baseline_discovered.completed,
        profile_linked: status.steps.profile_linked.completed,
        baseline_confirmed: status.steps.baseline_confirmed.completed,
      }
    : {
        market_added: false,
        initial_scrape: false,
        baseline_discovered: false,
        profile_linked: false,
        baseline_confirmed: false,
      };

  // Calculate current step
  const getCurrentStep = () => {
    if (!completedSteps.market_added) return 1;
    if (!completedSteps.initial_scrape) return 2;
    if (!completedSteps.baseline_discovered) return 3;
    if (!completedSteps.profile_linked) return 4;
    if (!completedSteps.baseline_confirmed) return 5;
    return 5; // All complete
  };

  const currentStep = getCurrentStep();
  const progressPercent = status?.progress_percent || (currentStep - 1) * 20;

  // Handlers
  const handleStep1Submit = async () => {
    const result = await startOnboarding.mutateAsync({
      theater_name: theaterName,
      circuit_name: circuitName === 'auto' ? undefined : circuitName || undefined,
      market,
    });
    if (result.circuit_name) {
      setCircuitName(result.circuit_name);
    }
  };

  const handleStep2Submit = async (source: 'fandango' | 'enttelligence', count: number) => {
    await recordScrape.mutateAsync({
      theaterName,
      source,
      count,
    });
  };

  const handleStep3Discover = async (lookbackDays: number, minSamples: number) => {
    const result = await discoverBaselines.mutateAsync({
      theaterName,
      lookback_days: lookbackDays,
      min_samples: minSamples,
    });
    setDiscoveryResult(result);
  };

  const handleStep4Link = async (circuit?: string) => {
    await linkProfile.mutateAsync({
      theaterName,
      circuit_name: circuit,
    });
  };

  const handleStep5Confirm = async (notes?: string) => {
    const result = await confirmBaselines.mutateAsync({
      theaterName,
      notes,
    });
    if (onComplete) {
      onComplete(result);
    }
  };

  const isLoading =
    startOnboarding.isPending ||
    recordScrape.isPending ||
    discoverBaselines.isPending ||
    linkProfile.isPending ||
    confirmBaselines.isPending;

  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Theater Onboarding
          {status?.onboarding_status === 'complete' && (
            <Badge variant="success">Complete</Badge>
          )}
        </CardTitle>
        <CardDescription>
          {theaterName
            ? `Onboarding ${theaterName}`
            : 'Add a new theater to the baseline system'}
        </CardDescription>
        <Progress value={progressPercent} className="mt-4" />
        <p className="text-xs text-muted-foreground mt-1">
          {progressPercent}% complete
        </p>
      </CardHeader>

      <CardContent>
        <StepIndicator
          steps={STEPS}
          currentStep={currentStep}
          completedSteps={completedSteps}
        />

        {currentStep === 1 && (
          <Step1Content
            theaterName={theaterName}
            setTheaterName={setTheaterName}
            market={market}
            setMarket={setMarket}
            circuitName={circuitName}
            setCircuitName={setCircuitName}
            onSubmit={handleStep1Submit}
            isLoading={startOnboarding.isPending}
          />
        )}

        {currentStep === 2 && (
          <Step2Content
            theaterName={theaterName}
            onSubmit={handleStep2Submit}
            isLoading={recordScrape.isPending}
          />
        )}

        {currentStep === 3 && (
          <Step3Content
            theaterName={theaterName}
            discoveryResult={discoveryResult}
            onDiscover={handleStep3Discover}
            isLoading={discoverBaselines.isPending}
          />
        )}

        {currentStep === 4 && (
          <Step4Content
            theaterName={theaterName}
            circuitName={status?.circuit_name || circuitName || null}
            onLink={handleStep4Link}
            isLoading={linkProfile.isPending}
          />
        )}

        {currentStep === 5 && status && (
          <Step5Content
            theaterName={theaterName}
            onConfirm={handleStep5Confirm}
            isLoading={confirmBaselines.isPending}
          />
        )}

        {status?.onboarding_status === 'complete' && (
          <div className="text-center py-8">
            <CheckCircle2 className="h-16 w-16 text-green-500 mx-auto mb-4" />
            <h3 className="text-lg font-semibold">Onboarding Complete!</h3>
            <p className="text-muted-foreground">
              {theaterName} is now fully onboarded with {status.steps.baseline_discovered.count || 0} baselines.
            </p>
          </div>
        )}
      </CardContent>

      {onCancel && (
        <CardFooter className="justify-between">
          <Button variant="ghost" onClick={onCancel} disabled={isLoading}>
            Cancel
          </Button>
        </CardFooter>
      )}
    </Card>
  );
}

export default TheaterOnboardingWizard;
