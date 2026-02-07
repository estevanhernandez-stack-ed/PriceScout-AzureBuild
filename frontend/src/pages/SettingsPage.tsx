/**
 * Settings Page
 *
 * Admin-only tabbed settings page for system configuration modifiers.
 * Centralizes tax estimation, name mapping, market scope, alerts, and diagnostics.
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { TaxConfigPanel } from '@/components/settings/TaxConfigPanel';
import { MarketScopePanel } from '@/components/settings/MarketScopePanel';
import { NameMappingPanel } from '@/components/settings/NameMappingPanel';
import { SystemDiagnosticsPanel } from '@/components/settings/SystemDiagnosticsPanel';

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState('tax');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground">
          System configuration for pricing analysis, theater matching, and data quality.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="tax">Tax Estimation</TabsTrigger>
          <TabsTrigger value="name-mapping">Name Mapping</TabsTrigger>
          <TabsTrigger value="market-scope">Market Scope</TabsTrigger>
          <TabsTrigger value="diagnostics">System Diagnostics</TabsTrigger>
        </TabsList>

        <TabsContent value="tax" className="space-y-4">
          <TaxConfigPanel />
        </TabsContent>

        <TabsContent value="name-mapping" className="space-y-4">
          <NameMappingPanel />
        </TabsContent>

        <TabsContent value="market-scope" className="space-y-4">
          <MarketScopePanel />
        </TabsContent>

        <TabsContent value="diagnostics" className="space-y-4">
          <SystemDiagnosticsPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
