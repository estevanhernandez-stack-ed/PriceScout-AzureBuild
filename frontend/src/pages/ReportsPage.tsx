import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { FileText, Download } from 'lucide-react';

const reportTypes = [
  {
    title: 'Daily Lineup',
    description: 'Complete showtime and pricing lineup for selected markets.',
    formats: ['PDF', 'CSV'],
  },
  {
    title: 'Price Comparison',
    description: 'Side-by-side price comparison across competitors.',
    formats: ['PDF', 'CSV'],
  },
  {
    title: 'Operating Hours',
    description: 'Theater operating hours and showtime distribution.',
    formats: ['CSV', 'JSON'],
  },
  {
    title: 'PLF Formats',
    description: 'Premium Large Format availability and pricing.',
    formats: ['CSV', 'JSON'],
  },
];

export function ReportsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Reports</h1>
        <p className="text-muted-foreground">
          Generate and download market analysis reports.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {reportTypes.map((report) => (
          <Card key={report.title}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-muted-foreground" />
                <CardTitle className="text-lg">{report.title}</CardTitle>
              </div>
              <CardDescription>{report.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                {report.formats.map((format) => (
                  <Button key={format} variant="outline" size="sm">
                    <Download className="mr-2 h-4 w-4" />
                    {format}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
