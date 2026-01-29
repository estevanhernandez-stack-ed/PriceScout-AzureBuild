import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { 
  useAuditLogs, 
  useAuditLogEventTypes, 
  useAuditLogCategories,
  getSeverityStyle,
  type AuditLogEntry
} from '@/hooks/api';
import { 
  Search, 
  Filter, 
  RefreshCw, 
  ChevronLeft, 
  ChevronRight,
  ClipboardList,
  Calendar,
  User,
  AlertCircle
} from 'lucide-react';
import { format } from 'date-fns';

export function AuditLogPage() {
  const [page, setPage] = useState(0);
  const [limit] = useState(50);
  const [filters, setFilters] = useState({
    username: '',
    eventType: 'all',
    eventCategory: 'all',
    severity: 'all',
    dateFrom: '',
    dateTo: ''
  });

  const { data, isLoading, refetch, isRefetching } = useAuditLogs({
    offset: page * limit,
    limit,
    ...filters
  });

  const { data: eventTypes } = useAuditLogEventTypes();
  const { data: categories } = useAuditLogCategories();

  const handleFilterChange = (key: string, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setPage(0);
  };

  const totalPages = data ? Math.ceil(data.total_count / limit) : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">System Audit Log</h1>
          <p className="text-muted-foreground">
            Track all administrative actions, security events, and system changes.
          </p>
        </div>
        <Button 
          variant="outline" 
          onClick={() => refetch()} 
          disabled={isLoading || isRefetching}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isRefetching ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <Card className="bg-card/50 backdrop-blur-sm border-none shadow-md">
        <CardContent className="pt-6">
          <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase text-muted-foreground flex items-center gap-1">
                <Search className="h-3 w-3" />
                Username
              </label>
              <Input 
                placeholder="Search user..." 
                value={filters.username}
                onChange={(e) => handleFilterChange('username', e.target.value)}
                className="h-9"
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase text-muted-foreground flex items-center gap-1">
                <ClipboardList className="h-3 w-3" />
                Event Type
              </label>
              <select 
                className="w-full h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={filters.eventType}
                onChange={(e) => handleFilterChange('eventType', e.target.value)}
              >
                <option value="all">All Types</option>
                {eventTypes?.map(type => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase text-muted-foreground flex items-center gap-1">
                <Filter className="h-3 w-3" />
                Category
              </label>
              <select 
                className="w-full h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={filters.eventCategory}
                onChange={(e) => handleFilterChange('eventCategory', e.target.value)}
              >
                <option value="all">All Categories</option>
                {categories?.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase text-muted-foreground flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                Severity
              </label>
              <select 
                className="w-full h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={filters.severity}
                onChange={(e) => handleFilterChange('severity', e.target.value)}
              >
                <option value="all">All Severities</option>
                <option value="info">Info</option>
                <option value="success">Success</option>
                <option value="warning">Warning</option>
                <option value="error">Error</option>
                <option value="critical">Critical</option>
              </select>
            </div>

            <div className="space-y-2 lg:col-span-2">
              <label className="text-xs font-semibold uppercase text-muted-foreground flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                Date Range
              </label>
              <div className="flex gap-2">
                <Input 
                  type="date" 
                  className="h-9" 
                  value={filters.dateFrom}
                  onChange={(e) => handleFilterChange('dateFrom', e.target.value)}
                />
                <Input 
                  type="date" 
                  className="h-9" 
                  value={filters.dateTo}
                  onChange={(e) => handleFilterChange('dateTo', e.target.value)}
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Log Table */}
      <Card className="border-none shadow-xl bg-card/50 overflow-hidden">
        <CardContent className="p-0">
          <Table>
            <TableHeader className="bg-muted/50">
              <TableRow>
                <TableHead className="w-[180px]">Timestamp</TableHead>
                <TableHead className="w-[120px]">User</TableHead>
                <TableHead className="w-[150px]">Event Type</TableHead>
                <TableHead className="w-[120px]">Category</TableHead>
                <TableHead className="w-[100px]">Severity</TableHead>
                <TableHead>Details</TableHead>
                <TableHead className="w-[120px]">IP Address</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7} className="h-12 animate-pulse bg-muted/20" />
                  </TableRow>
                ))
              ) : data?.entries.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-64 text-center text-muted-foreground">
                    No audit logs found matching your criteria.
                  </TableCell>
                </TableRow>
              ) : (
                data?.entries.map((entry: AuditLogEntry) => (
                  <TableRow key={entry.log_id} className="hover:bg-muted/30 transition-colors">
                    <TableCell className="text-xs font-mono">
                      {format(new Date(entry.timestamp), 'MMM dd, HH:mm:ss')}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <User className="h-3 w-3 text-muted-foreground" />
                        <span className="text-sm font-medium">{entry.username || 'System'}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
                        {entry.event_type}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground capitalize">
                      {entry.event_category}
                    </TableCell>
                    <TableCell>
                      <Badge className={`text-[10px] uppercase ${getSeverityStyle(entry.severity)}`}>
                        {entry.severity}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm">
                      <div className="max-w-[400px] truncate" title={entry.details || ''}>
                        {entry.details}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs font-mono text-muted-foreground">
                      {entry.ip_address || '—'}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between px-2">
        <p className="text-sm text-muted-foreground">
          Showing {page * limit + 1} to {Math.min((page + 1) * limit, data?.total_count || 0)} of {data?.total_count || 0} entries
        </p>
        <div className="flex items-center gap-2">
          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
          >
            <ChevronLeft className="h-4 w-4 mr-1" />
            Previous
          </Button>
          <div className="text-sm font-medium px-4">
            Page {page + 1} of {totalPages || 1}
          </div>
          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => setPage(p => p + 1)}
            disabled={page >= totalPages - 1}
          >
            Next
            <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      </div>
    </div>
  );
}
