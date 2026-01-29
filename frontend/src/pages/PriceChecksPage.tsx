import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function PriceChecksPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Price Checks</h1>
        <p className="text-muted-foreground">
          View historical price data and comparisons.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Price History</CardTitle>
          <CardDescription>
            Search and filter price check records.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Price check table will be displayed here once connected to the API.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
