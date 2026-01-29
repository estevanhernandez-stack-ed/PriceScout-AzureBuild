# Role-Based Access Control (RBAC) Implementation

This document details the implementation of granular Role-Based Access Control (RBAC) in PriceScout ENT, introduced in January 2026 to support enterprise-grade security and delegated operations.

## Overview

The RBAC system has been expanded beyond simple `admin`/`user` roles to include specialized roles that align with enterprise organizational structures. This allows for the principle of least privilege, ensuring users only have the access necessary for their specific functions.

## User Roles

| Role         | Description                  | Key Permissions                                                                                        |
| :----------- | :--------------------------- | :----------------------------------------------------------------------------------------------------- |
| **Admin**    | Full system access.          | User management, system configuration, all data access, circuit breaker control (trip/reset).          |
| **Manager**  | Operational leadership.      | View all analytics, manage data, acknowledge alerts, view system health. Cannot manage admin users.    |
| **Operator** | Day-to-day operations staff. | Trigger data syncs, manage scrape jobs, acknowledge alerts, reset (but not trip) circuit breakers.     |
| **Auditor**  | Compliance and oversight.    | Read-only access to almost all system data, including audit logs and user lists. No write permissions. |
| **User**     | Standard viewer.             | View dashboards and basic reports. Cannot view system health or administrative data.                   |

## Technical Implementation

### 1. Backend Dependencies (`api/routers/auth.py`)

We use FastAPI dependencies to enforce role requirements at the route level. These are atomic and reusable across all routers.

- `require_admin`: Only users with the `admin` role.
- `require_operator`: `admin`, `manager`, or `operator`. (Used for operational write tasks).
- `require_auditor`: `admin` or `auditor`. (Used for sensitive read-only tasks like audit logs).
- `require_read_admin`: `admin`, `manager`, `operator`, or `auditor`. (Used for general administrative visibility).

### 2. Frontend Authorization (`frontend/src/components/auth/ProtectedRoute.tsx`)

The `ProtectedRoute` component has been enhanced to support:

- **Multiple Roles**: Accepts an array of roles (e.g., `requiredRole={['admin', 'operator']}`).
- **Role Hierarchy**: Automatically allows higher-level roles to bypass checks for lower-level requirements.
- **Dynamic Fallbacks**: Redirects unauthorized users with an "Access Denied" message and a "Go Back" option.

### 3. Dynamic UI Filtering (`frontend/src/components/layout/MainLayout.tsx`)

The main navigation sidebar now dynamically filters components based on the user's role:

- **Management Section**: Only visible to those with `hasAdminAccess` (Admin, Manager, Operator, Auditor).
- **Tool-Specific Visibility**:
  - `System Health` is visible to all management roles.
  - `Data Management` and `Repair Queue` are hidden from `Auditor`.
  - `Users` is hidden from `Operator`.

## Operational Workflows

### Scrape & Sync Operations

- **Triggering**: Restricted to `admin`, `manager`, and `operator`.
- **Viewing Logs**: Available to `auditor` and higher.

### Circuit Breaker Management

The system now includes safety-critical controls for external API protection:

- **Tripping**: Restricted to `admin`. (Manually forcing a circuit to OPEN to stop all traffic).
- **Resetting**: Available to `admin`, `manager`, and `operator`. (Testing and restoring connectivity after an issue).

## Future Roadmap: Company-Level RBAC

The current implementation provides robust functional roles. The next phase of development will involve:

1. **Hierarchical Company Mapping**: Mapping these functional roles (`operator`, `auditor`) to company-specific levels (e.g., Level 1 Operator, Region Auditor).
2. **Contextual Permissions**: Roles that are tied to specific theater groups or markets, rather than global company access.
3. **Custom Policy Engine**: Allowing administrators to define custom role mappings based on their own internal organizational tiers.

---

**Last Updated:** January 14, 2026
**Version:** 1.2.0 (ENT Security Update)
