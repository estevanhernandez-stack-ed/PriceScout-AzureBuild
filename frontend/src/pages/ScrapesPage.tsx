import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function ScrapesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Scrapes</h1>
        <p className="text-muted-foreground">
          Manage scrape sources and view scrape history.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Scrape Sources</CardTitle>
            <CardDescription>
              Configure and manage data collection sources.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Scrape sources will be displayed here once connected to the API.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Jobs</CardTitle>
            <CardDescription>
              View status of recent scrape jobs.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Scrape jobs will be displayed here once connected to the API.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
