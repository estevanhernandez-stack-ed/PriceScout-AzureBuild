/**
 * Tax Configuration Panel
 *
 * Allows users to configure estimated tax rates for EntTelligence prices.
 * Supports a company-wide default rate and per-state overrides.
 */

import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Receipt,
  Plus,
  Trash2,
  Save,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { useTaxConfig, useUpdateTaxConfig } from '@/hooks/api';
import { useToast } from '@/hooks/use-toast';

/** Common US state tax rates for theater tickets */
const COMMON_STATE_RATES: Record<string, number> = {
  WI: 0.055,
  TX: 0.0625,
  CA: 0.0725,
  NY: 0.08,
  FL: 0.06,
  IL: 0.0625,
  OH: 0.0575,
  GA: 0.04,
  PA: 0.06,
  NC: 0.0475,
  NJ: 0.0663,
  VA: 0.053,
  MI: 0.06,
  MN: 0.0688,
  CO: 0.029,
  TN: 0.07,
  MO: 0.0423,
  IN: 0.07,
  MA: 0.0625,
  AZ: 0.056,
};

/** US state name lookup */
const STATE_NAMES: Record<string, string> = {
  WI: 'Wisconsin', TX: 'Texas', CA: 'California', NY: 'New York',
  FL: 'Florida', IL: 'Illinois', OH: 'Ohio', GA: 'Georgia',
  PA: 'Pennsylvania', NC: 'North Carolina', NJ: 'New Jersey',
  VA: 'Virginia', MI: 'Michigan', MN: 'Minnesota', CO: 'Colorado',
  TN: 'Tennessee', MO: 'Missouri', IN: 'Indiana', MA: 'Massachusetts',
  AZ: 'Arizona',
};

export function TaxConfigPanel() {
  const { toast } = useToast();
  const { data: taxConfig, isLoading } = useTaxConfig();
  const updateTaxConfig = useUpdateTaxConfig();

  // Local form state
  const [enabled, setEnabled] = useState(false);
  const [defaultRate, setDefaultRate] = useState('7.5');
  const [perState, setPerState] = useState<Record<string, number>>({});
  const [newStateCode, setNewStateCode] = useState('');
  const [newStateRate, setNewStateRate] = useState('');
  const [hasChanges, setHasChanges] = useState(false);

  // Sync from API data
  useEffect(() => {
    if (taxConfig) {
      setEnabled(taxConfig.enabled);
      setDefaultRate((taxConfig.default_rate * 100).toFixed(2));
      setPerState(taxConfig.per_state);
      setHasChanges(false);
    }
  }, [taxConfig]);

  const handleSave = async () => {
    const rate = parseFloat(defaultRate) / 100;
    if (isNaN(rate) || rate < 0 || rate > 0.25) {
      toast({
        title: 'Invalid Rate',
        description: 'Default tax rate must be between 0% and 25%.',
        variant: 'destructive',
      });
      return;
    }

    try {
      await updateTaxConfig.mutateAsync({
        enabled,
        default_rate: rate,
        per_state: perState,
      });
      toast({
        title: 'Tax Config Saved',
        description: `Default rate: ${defaultRate}%, ${Object.keys(perState).length} state overrides.`,
      });
      setHasChanges(false);
    } catch {
      toast({
        title: 'Save Failed',
        description: 'Could not save tax configuration.',
        variant: 'destructive',
      });
    }
  };

  const handleAddState = () => {
    const code = newStateCode.toUpperCase().trim();
    const rate = parseFloat(newStateRate);

    if (!code || code.length !== 2) {
      toast({ title: 'Invalid State', description: 'Enter a 2-letter state code.', variant: 'destructive' });
      return;
    }
    if (isNaN(rate) || rate < 0 || rate > 25) {
      toast({ title: 'Invalid Rate', description: 'Rate must be between 0% and 25%.', variant: 'destructive' });
      return;
    }

    setPerState(prev => ({ ...prev, [code]: rate / 100 }));
    setNewStateCode('');
    setNewStateRate('');
    setHasChanges(true);
  };

  const handleRemoveState = (code: string) => {
    setPerState(prev => {
      const next = { ...prev };
      delete next[code];
      return next;
    });
    setHasChanges(true);
  };

  const handleAutoPopulate = () => {
    setPerState(prev => {
      const merged = { ...prev };
      for (const [code, rate] of Object.entries(COMMON_STATE_RATES)) {
        if (!(code in merged)) {
          merged[code] = rate;
        }
      }
      return merged;
    });
    setHasChanges(true);
    toast({
      title: 'States Added',
      description: 'Common US state tax rates have been populated. Existing overrides were preserved.',
    });
  };

  const markChanged = () => setHasChanges(true);

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-12 flex justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  const sortedStates = Object.entries(perState).sort(([a], [b]) => a.localeCompare(b));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Receipt className="h-5 w-5 text-green-600" />
          Estimated Tax Configuration
          {hasChanges && (
            <Badge variant="outline" className="bg-yellow-100 text-yellow-700">
              Unsaved Changes
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          Configure estimated tax rates to adjust EntTelligence base prices for comparison
          with Fandango&apos;s tax-inclusive prices. Raw stored prices are never modified.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Enable Toggle */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label className="text-base">Enable Tax Estimation</Label>
            <p className="text-sm text-muted-foreground">
              When enabled, EntTelligence prices will include estimated tax in comparisons
            </p>
          </div>
          <Switch
            checked={enabled}
            onCheckedChange={(checked) => {
              setEnabled(checked);
              markChanged();
            }}
          />
        </div>

        {/* Default Rate */}
        <div className="space-y-2">
          <Label>Default Tax Rate (%)</Label>
          <div className="flex items-center gap-2 max-w-xs">
            <Input
              type="number"
              step="0.25"
              min="0"
              max="25"
              value={defaultRate}
              onChange={(e) => {
                setDefaultRate(e.target.value);
                markChanged();
              }}
              placeholder="7.5"
            />
            <span className="text-muted-foreground">%</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Applied to all theaters unless a per-state override exists. US average is ~7.5%.
          </p>
        </div>

        {/* Per-State Overrides */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label className="text-base">Per-State Overrides</Label>
            <Button variant="outline" size="sm" onClick={handleAutoPopulate}>
              <Sparkles className="h-3 w-3 mr-1" />
              Auto-populate US Rates
            </Button>
          </div>

          {sortedStates.length > 0 ? (
            <div className="rounded-md border max-h-[300px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>State</TableHead>
                    <TableHead>Rate</TableHead>
                    <TableHead className="w-[60px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedStates.map(([code, rate]) => (
                    <TableRow key={code}>
                      <TableCell className="font-medium">
                        {code}
                        {STATE_NAMES[code] && (
                          <span className="text-muted-foreground ml-2 text-sm">
                            {STATE_NAMES[code]}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="font-mono">
                        {(rate * 100).toFixed(2)}%
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveState(code)}
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No per-state overrides configured. All theaters will use the default rate.
            </p>
          )}

          {/* Add new state */}
          <div className="flex items-end gap-2">
            <div className="space-y-1">
              <Label className="text-xs">State Code</Label>
              <Input
                value={newStateCode}
                onChange={(e) => setNewStateCode(e.target.value)}
                placeholder="WI"
                maxLength={2}
                className="w-20 uppercase"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Rate (%)</Label>
              <Input
                type="number"
                step="0.25"
                min="0"
                max="25"
                value={newStateRate}
                onChange={(e) => setNewStateRate(e.target.value)}
                placeholder="5.5"
                className="w-24"
              />
            </div>
            <Button variant="outline" size="sm" onClick={handleAddState}>
              <Plus className="h-3 w-3 mr-1" />
              Add
            </Button>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end pt-2">
          <Button
            onClick={handleSave}
            disabled={!hasChanges || updateTaxConfig.isPending}
          >
            {updateTaxConfig.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Save Tax Configuration
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
