import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
  UserPlus,
  Users,
  Shield,
  ShieldCheck,
  ShieldAlert,
  Pencil,
  Trash2,
  Key,
  RefreshCw,
  Search,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Activity,
} from 'lucide-react';
import {
  useUsers,
  useCreateUser,
  useUpdateUser,
  useDeleteUser,
  useResetPassword,
} from '@/hooks/api/useUsers';
import type { UserRole, HomeLocationType } from '@/types';

interface UserFormData {
  username: string;
  role: UserRole;
  company: string;
  default_company: string;
  home_location_type: HomeLocationType | '';
  home_location_value: string;
  is_active: boolean;
}

const ROLES: { value: string; label: string; icon: React.ElementType }[] = [
  { value: 'admin', label: 'Admin', icon: ShieldAlert },
  { value: 'manager', label: 'Manager', icon: ShieldCheck },
  { value: 'operator', label: 'Operator', icon: Activity },
  { value: 'auditor', label: 'Auditor', icon: Search },
  { value: 'user', label: 'User', icon: Shield },
];

const HOME_LOCATION_TYPES: { value: HomeLocationType; label: string }[] = [
  { value: 'director', label: 'Director' },
  { value: 'market', label: 'Market' },
  { value: 'theater', label: 'Theater' },
];

const getRoleBadgeClass = (role: string) => {
  switch (role) {
    case 'admin':
      return 'bg-red-500/10 text-red-500';
    case 'manager':
      return 'bg-blue-500/10 text-blue-500';
    case 'operator':
      return 'bg-amber-500/10 text-amber-500';
    case 'auditor':
      return 'bg-purple-500/10 text-purple-500';
    default:
      return 'bg-gray-500/10 text-gray-500';
  }
};

export function AdminUsersPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showResetPasswordDialog, setShowResetPasswordDialog] = useState(false);
  const [selectedUser, setSelectedUser] = useState<{ user_id: number; username: string } | null>(null);
  const [formData, setFormData] = useState<UserFormData>({
    username: '',
    role: 'user',
    company: '',
    default_company: '',
    home_location_type: '',
    home_location_value: '',
    is_active: true,
  });
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const { data: usersData, isLoading, refetch } = useUsers({
    role: roleFilter !== 'all' ? roleFilter : undefined,
  });
  const createMutation = useCreateUser();
  const updateMutation = useUpdateUser();
  const deleteMutation = useDeleteUser();
  const resetPasswordMutation = useResetPassword();

  const users = usersData?.users || [];
  const filteredUsers = users.filter(user =>
    user.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (user.company?.toLowerCase() || '').includes(searchQuery.toLowerCase())
  );

  // Summary stats
  const stats = {
    total: users.length,
    active: users.filter(u => u.is_active).length,
    admins: users.filter(u => u.role === 'admin').length,
    managers: users.filter(u => u.role === 'manager').length,
  };

  const resetForm = () => {
    setFormData({
      username: '',
      role: 'user',
      company: '',
      default_company: '',
      home_location_type: '',
      home_location_value: '',
      is_active: true,
    });
    setNewPassword('');
    setConfirmPassword('');
  };

  const handleCreate = async () => {
    if (!formData.username || !newPassword) return;

    try {
      await createMutation.mutateAsync({
        username: formData.username,
        password: newPassword,
        role: formData.role,
        company: formData.company || undefined,
        default_company: formData.default_company || undefined,
        home_location_type: formData.home_location_type || undefined,
        home_location_value: formData.home_location_value || undefined,
      });
      setShowCreateDialog(false);
      resetForm();
    } catch (error) {
      console.error('Failed to create user:', error);
    }
  };

  const handleEdit = async () => {
    if (!selectedUser) return;

    try {
      await updateMutation.mutateAsync({
        userId: selectedUser.user_id,
        data: {
          username: formData.username || undefined,
          role: formData.role,
          company: formData.company || undefined,
          default_company: formData.default_company || undefined,
          home_location_type: formData.home_location_type || undefined,
          home_location_value: formData.home_location_value || undefined,
          is_active: formData.is_active,
        },
      });
      setShowEditDialog(false);
      resetForm();
      setSelectedUser(null);
    } catch (error) {
      console.error('Failed to update user:', error);
    }
  };

  const handleDelete = async () => {
    if (!selectedUser) return;

    try {
      await deleteMutation.mutateAsync(selectedUser.user_id);
      setShowDeleteDialog(false);
      setSelectedUser(null);
    } catch (error) {
      console.error('Failed to delete user:', error);
    }
  };

  const handleResetPassword = async () => {
    if (!selectedUser || !newPassword || newPassword !== confirmPassword) return;

    try {
      await resetPasswordMutation.mutateAsync({
        userId: selectedUser.user_id,
        data: { new_password: newPassword },
      });
      setShowResetPasswordDialog(false);
      setNewPassword('');
      setConfirmPassword('');
      setSelectedUser(null);
    } catch (error) {
      console.error('Failed to reset password:', error);
    }
  };

  const openEditDialog = (user: typeof users[0]) => {
    setSelectedUser({ user_id: user.user_id, username: user.username });
    setFormData({
      username: user.username,
      role: user.role as UserRole,
      company: user.company || '',
      default_company: user.default_company || '',
      home_location_type: (user.home_location_type as HomeLocationType) || '',
      home_location_value: user.home_location_value || '',
      is_active: user.is_active,
    });
    setShowEditDialog(true);
  };

  const openDeleteDialog = (user: typeof users[0]) => {
    setSelectedUser({ user_id: user.user_id, username: user.username });
    setShowDeleteDialog(true);
  };

  const openResetPasswordDialog = (user: typeof users[0]) => {
    setSelectedUser({ user_id: user.user_id, username: user.username });
    setNewPassword('');
    setConfirmPassword('');
    setShowResetPasswordDialog(true);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">User Management</h1>
          <p className="text-muted-foreground">
            Manage user accounts and permissions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button onClick={() => { resetForm(); setShowCreateDialog(true); }}>
            <UserPlus className="mr-2 h-4 w-4" />
            Add User
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Total Users</span>
            </div>
            <p className="text-3xl font-bold mt-2">{stats.total}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              <span className="text-sm text-muted-foreground">Active</span>
            </div>
            <p className="text-3xl font-bold mt-2">{stats.active}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-red-500" />
              <span className="text-sm text-muted-foreground">Admins</span>
            </div>
            <p className="text-3xl font-bold mt-2">{stats.admins}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-blue-500" />
              <span className="text-sm text-muted-foreground">Managers</span>
            </div>
            <p className="text-3xl font-bold mt-2">{stats.managers}</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search users..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8"
              />
            </div>
            <div>
              <Label className="sr-only">Role Filter</Label>
              <select
                className="p-2 border rounded-md bg-background"
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
              >
                <option value="all">All Roles</option>
                <option value="admin">Admin</option>
                <option value="manager">Manager</option>
                <option value="user">User</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Users Table */}
      <Card>
        <CardHeader>
          <CardTitle>Users</CardTitle>
          <CardDescription>
            {filteredUsers.length} users found
          </CardDescription>
        </CardHeader>
        <CardContent>
          {filteredUsers.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No users found. Add a user to get started.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Username</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Home Location</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Login</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.map((user) => (
                  <TableRow key={user.user_id}>
                    <TableCell className="font-medium">{user.username}</TableCell>
                    <TableCell>
                      <Badge className={getRoleBadgeClass(user.role)}>
                        {user.role}
                      </Badge>
                    </TableCell>
                    <TableCell>{user.company || '—'}</TableCell>
                    <TableCell>
                      {user.home_location_type ? (
                        <span className="text-sm">
                          <span className="text-muted-foreground capitalize">{user.home_location_type}:</span>{' '}
                          {user.home_location_value || '—'}
                        </span>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell>
                      {user.is_active ? (
                        <Badge className="bg-green-500/10 text-green-500">
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          Active
                        </Badge>
                      ) : (
                        <Badge className="bg-gray-500/10 text-gray-500">
                          <XCircle className="h-3 w-3 mr-1" />
                          Inactive
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {user.last_login
                        ? new Date(user.last_login).toLocaleDateString()
                        : 'Never'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditDialog(user)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openResetPasswordDialog(user)}
                        >
                          <Key className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openDeleteDialog(user)}
                          className="text-red-500 hover:text-red-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create User Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New User</DialogTitle>
            <DialogDescription>
              Add a new user to the system
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="role">Role</Label>
                <select
                  id="role"
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value as UserRole })}
                >
                  {ROLES.map((role) => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="company">Company</Label>
                <Input
                  id="company"
                  value={formData.company}
                  onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="default_company">Default Company</Label>
                <Input
                  id="default_company"
                  value={formData.default_company}
                  onChange={(e) => setFormData({ ...formData, default_company: e.target.value })}
                  className="mt-1"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="home_location_type">Home Location Type</Label>
                <select
                  id="home_location_type"
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={formData.home_location_type}
                  onChange={(e) => setFormData({ ...formData, home_location_type: e.target.value as HomeLocationType | '' })}
                >
                  <option value="">None</option>
                  {HOME_LOCATION_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="home_location_value">Home Location Value</Label>
                <Input
                  id="home_location_value"
                  value={formData.home_location_value}
                  onChange={(e) => setFormData({ ...formData, home_location_value: e.target.value })}
                  className="mt-1"
                  placeholder={formData.home_location_type ? `Enter ${formData.home_location_type} name` : 'Select type first'}
                  disabled={!formData.home_location_type}
                />
              </div>
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Min 8 chars, uppercase, lowercase, number, special char
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!formData.username || !newPassword || createMutation.isPending}
            >
              {createMutation.isPending ? 'Creating...' : 'Create User'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>
              Update user details for {selectedUser?.username}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="edit_username">Username</Label>
                <Input
                  id="edit_username"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="edit_role">Role</Label>
                <select
                  id="edit_role"
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value as UserRole })}
                >
                  {ROLES.map((role) => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="edit_company">Company</Label>
                <Input
                  id="edit_company"
                  value={formData.company}
                  onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="edit_default_company">Default Company</Label>
                <Input
                  id="edit_default_company"
                  value={formData.default_company}
                  onChange={(e) => setFormData({ ...formData, default_company: e.target.value })}
                  className="mt-1"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="edit_home_location_type">Home Location Type</Label>
                <select
                  id="edit_home_location_type"
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={formData.home_location_type}
                  onChange={(e) => setFormData({ ...formData, home_location_type: e.target.value as HomeLocationType | '' })}
                >
                  <option value="">None</option>
                  {HOME_LOCATION_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="edit_home_location_value">Home Location Value</Label>
                <Input
                  id="edit_home_location_value"
                  value={formData.home_location_value}
                  onChange={(e) => setFormData({ ...formData, home_location_value: e.target.value })}
                  className="mt-1"
                  placeholder={formData.home_location_type ? `Enter ${formData.home_location_type} name` : 'Select type first'}
                  disabled={!formData.home_location_type}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="edit_is_active"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              />
              <Label htmlFor="edit_is_active">Active</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleEdit} disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete User Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-500">
              <AlertTriangle className="h-5 w-5" />
              Delete User
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to delete user "{selectedUser?.username}"? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete User'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset Password Dialog */}
      <Dialog open={showResetPasswordDialog} onOpenChange={setShowResetPasswordDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset Password</DialogTitle>
            <DialogDescription>
              Set a new password for {selectedUser?.username}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="new_password">New Password</Label>
              <Input
                id="new_password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Min 8 chars, uppercase, lowercase, number, special char
              </p>
            </div>
            <div>
              <Label htmlFor="confirm_password">Confirm Password</Label>
              <Input
                id="confirm_password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="mt-1"
              />
              {confirmPassword && newPassword !== confirmPassword && (
                <p className="text-xs text-red-500 mt-1">Passwords do not match</p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowResetPasswordDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleResetPassword}
              disabled={!newPassword || newPassword !== confirmPassword || resetPasswordMutation.isPending}
            >
              {resetPasswordMutation.isPending ? 'Resetting...' : 'Reset Password'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
