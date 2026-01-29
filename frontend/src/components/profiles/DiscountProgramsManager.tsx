import { useState } from 'react';
import {
  Plus,
  Trash2,
  Edit2,
  Calendar,
  DollarSign,
  Percent,
  Tag,
  Check,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  useDiscountPrograms,
  useCreateDiscountProgram,
  useDeleteDiscountProgram,
  type DiscountProgram,
  type CreateDiscountProgramRequest,
} from '@/hooks/api/useDiscountPrograms';

// =============================================================================
// TYPES
// =============================================================================

interface DiscountProgramsManagerProps {
  circuitName: string;
  className?: string;
}

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

const DISCOUNT_TYPES = [
  { value: 'flat_price', label: 'Flat Price', icon: <DollarSign className="h-4 w-4" /> },
  { value: 'percentage_off', label: 'Percentage Off', icon: <Percent className="h-4 w-4" /> },
  { value: 'amount_off', label: 'Amount Off', icon: <Tag className="h-4 w-4" /> },
];

// =============================================================================
// ADD/EDIT DIALOG COMPONENT
// =============================================================================

interface ProgramDialogProps {
  circuitName: string;
  program?: DiscountProgram;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function ProgramDialog({ circuitName, program, open, onOpenChange }: ProgramDialogProps) {
  const createProgram = useCreateDiscountProgram();
  const isEditing = !!program;

  const [formData, setFormData] = useState<CreateDiscountProgramRequest>({
    program_name: program?.program_name || '',
    day_of_week: program?.day_of_week ?? 1,
    discount_type: program?.discount_type || 'flat_price',
    discount_value: program?.discount_value || 5,
    applicable_ticket_types: program?.applicable_ticket_types || undefined,
    applicable_formats: program?.applicable_formats || undefined,
    applicable_dayparts: program?.applicable_dayparts || undefined,
  });

  const handleSubmit = async () => {
    await createProgram.mutateAsync({
      circuitName,
      ...formData,
    });
    onOpenChange(false);
  };

  const getDiscountLabel = () => {
    switch (formData.discount_type) {
      case 'flat_price':
        return `$${formData.discount_value.toFixed(2)}`;
      case 'percentage_off':
        return `${formData.discount_value}% off`;
      case 'amount_off':
        return `$${formData.discount_value.toFixed(2)} off`;
      default:
        return '';
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? 'Edit Discount Program' : 'Add Discount Program'}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Update the discount program details.'
              : `Create a new discount program for ${circuitName}.`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="program-name">Program Name</Label>
            <Input
              id="program-name"
              placeholder="e.g., $5 Tuesdays"
              value={formData.program_name}
              onChange={(e) =>
                setFormData({ ...formData, program_name: e.target.value })
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Day of Week</Label>
              <Select
                value={String(formData.day_of_week)}
                onValueChange={(v) =>
                  setFormData({ ...formData, day_of_week: parseInt(v, 10) })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DAY_NAMES.map((day, index) => (
                    <SelectItem key={day} value={String(index)}>
                      {day}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Discount Type</Label>
              <Select
                value={formData.discount_type}
                onValueChange={(v) =>
                  setFormData({
                    ...formData,
                    discount_type: v as CreateDiscountProgramRequest['discount_type'],
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DISCOUNT_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      <span className="flex items-center gap-2">
                        {type.icon}
                        {type.label}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="discount-value">
              {formData.discount_type === 'flat_price'
                ? 'Price ($)'
                : formData.discount_type === 'percentage_off'
                ? 'Percentage (%)'
                : 'Amount Off ($)'}
            </Label>
            <Input
              id="discount-value"
              type="number"
              step={formData.discount_type === 'percentage_off' ? '1' : '0.01'}
              min={0}
              max={formData.discount_type === 'percentage_off' ? 100 : undefined}
              value={formData.discount_value}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  discount_value: parseFloat(e.target.value) || 0,
                })
              }
            />
          </div>

          <div className="p-3 bg-muted/50 rounded-lg">
            <p className="text-sm text-muted-foreground">
              Preview:{' '}
              <span className="font-medium text-foreground">
                {formData.program_name || 'Discount'} - Every{' '}
                {DAY_NAMES[formData.day_of_week]} at {getDiscountLabel()}
              </span>
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!formData.program_name || createProgram.isPending}
          >
            {createProgram.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Check className="mr-2 h-4 w-4" />
                {isEditing ? 'Update Program' : 'Create Program'}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// DELETE CONFIRMATION DIALOG
// =============================================================================

interface DeleteDialogProps {
  program: DiscountProgram | null;
  circuitName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function DeleteDialog({ program, circuitName, open, onOpenChange }: DeleteDialogProps) {
  const deleteProgram = useDeleteDiscountProgram();

  const handleDelete = async () => {
    if (!program) return;
    await deleteProgram.mutateAsync({
      circuitName,
      programId: program.program_id,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            Delete Discount Program
          </DialogTitle>
          <DialogDescription>
            Are you sure you want to delete "{program?.program_name}"? This action cannot
            be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleteProgram.isPending}
          >
            {deleteProgram.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Deleting...
              </>
            ) : (
              <>
                <Trash2 className="mr-2 h-4 w-4" />
                Delete Program
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// PROGRAM ROW COMPONENT
// =============================================================================

interface ProgramRowProps {
  program: DiscountProgram;
  onEdit: () => void;
  onDelete: () => void;
}

function ProgramRow({ program, onEdit, onDelete }: ProgramRowProps) {
  const getDiscountDisplay = () => {
    switch (program.discount_type) {
      case 'flat_price':
        return `$${program.discount_value.toFixed(2)}`;
      case 'percentage_off':
        return `${program.discount_value}% off`;
      case 'amount_off':
        return `$${program.discount_value.toFixed(2)} off`;
      default:
        return '-';
    }
  };

  const getConfidenceBadge = () => {
    const score = program.confidence_score;
    if (score >= 0.8) return <Badge variant="success">High ({(score * 100).toFixed(0)}%)</Badge>;
    if (score >= 0.5) return <Badge variant="warning">Medium ({(score * 100).toFixed(0)}%)</Badge>;
    return <Badge variant="outline">Low ({(score * 100).toFixed(0)}%)</Badge>;
  };

  const getSourceBadge = () => {
    switch (program.source) {
      case 'manual':
        return <Badge variant="info">Manual</Badge>;
      case 'auto_discovery':
        return <Badge variant="secondary">Auto</Badge>;
      default:
        return <Badge variant="outline">{program.source}</Badge>;
    }
  };

  return (
    <TableRow>
      <TableCell className="font-medium">{program.program_name}</TableCell>
      <TableCell>
        <Badge variant="outline">
          <Calendar className="mr-1 h-3 w-3" />
          {program.day_name}
        </Badge>
      </TableCell>
      <TableCell>
        <span className="font-mono">{getDiscountDisplay()}</span>
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-1">
          {program.applicable_ticket_types ? (
            program.applicable_ticket_types.map((t) => (
              <Badge key={t} variant="outline" className="text-xs">
                {t}
              </Badge>
            ))
          ) : (
            <span className="text-muted-foreground text-xs">All</span>
          )}
        </div>
      </TableCell>
      <TableCell>{getConfidenceBadge()}</TableCell>
      <TableCell>{getSourceBadge()}</TableCell>
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={onEdit}>
            <Edit2 className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={onDelete} className="text-destructive">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function DiscountProgramsManager({
  circuitName,
  className,
}: DiscountProgramsManagerProps) {
  const { data: programs, isLoading, error } = useDiscountPrograms(circuitName, false);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editProgram, setEditProgram] = useState<DiscountProgram | null>(null);
  const [deleteProgram, setDeleteProgram] = useState<DiscountProgram | null>(null);

  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center py-12 text-destructive">
          <AlertCircle className="h-5 w-5 mr-2" />
          Failed to load discount programs
        </CardContent>
      </Card>
    );
  }

  const activePrograms = programs?.filter((p) => p.is_active) || [];

  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Discount Programs</CardTitle>
          <CardDescription>
            Manage recurring discount days for {circuitName}
          </CardDescription>
        </div>
        <Button onClick={() => setAddDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Program
        </Button>
      </CardHeader>

      <CardContent>
        {activePrograms.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <Calendar className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>No discount programs configured yet.</p>
            <p className="text-sm mt-1">
              Add programs to track recurring discounts like "$5 Tuesdays".
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Program</TableHead>
                <TableHead>Day</TableHead>
                <TableHead>Discount</TableHead>
                <TableHead>Applies To</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {activePrograms.map((program) => (
                <ProgramRow
                  key={program.program_id}
                  program={program}
                  onEdit={() => setEditProgram(program)}
                  onDelete={() => setDeleteProgram(program)}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {/* Add Dialog */}
      <ProgramDialog
        circuitName={circuitName}
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
      />

      {/* Edit Dialog */}
      {editProgram && (
        <ProgramDialog
          circuitName={circuitName}
          program={editProgram}
          open={!!editProgram}
          onOpenChange={(open) => !open && setEditProgram(null)}
        />
      )}

      {/* Delete Dialog */}
      <DeleteDialog
        circuitName={circuitName}
        program={deleteProgram}
        open={!!deleteProgram}
        onOpenChange={(open) => !open && setDeleteProgram(null)}
      />
    </Card>
  );
}

export default DiscountProgramsManager;
