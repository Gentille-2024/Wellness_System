import { Navigate } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { can } from '../auth/access'

/**
 * Wrap a page with this to require login, and optionally:
 *   perms        -> the user needs ANY of these permissions
 *   exact        -> check the permission list itself (the super admin's
 *                   "all permissions" doesn't count; for company/employee pages)
 *   needsCompany -> the user must work for a company
 */
export default function ProtectedRoute({ perms, exact = false, needsCompany = false, children }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="page-center">Loading…</div>
  if (!user) return <Navigate to="/login" replace />

  const allowed = !perms || (exact ? perms.some((perm) => user.role_permissions.includes(perm)) : can(user, ...perms))
  if (!allowed || (needsCompany && !user.company)) return <Navigate to="/" replace />

  return children
}
