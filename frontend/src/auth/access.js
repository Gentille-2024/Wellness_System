// What a user may do is decided by their PERMISSIONS (which come from their
// roles). Roles can be created in the app, so screens never check role names.

// Does this user have at least one of these permissions?  can(user, 'record_visits')
export function can(user, ...permissions) {
  if (!user) return false
  if (user.is_superuser) return true
  return permissions.some((permission) => user.permissions?.includes(permission))
}

// The three areas of the app and the permissions that open them
export const EUCL_PERMISSIONS = ['manage_companies', 'manage_users', 'view_all_visits', 'manage_payments', 'manage_employees']
export const COMPANY_PERMISSIONS = [
  'view_company_dashboard',
  'record_visits',
  'take_attendance',
  'view_company_services',
  'view_employees_attended',
  'view_company_visits',
  'manage_company_services',
  'manage_company_staff',
]

// Company pages in menu order, and the permissions that open each one
// (a company user lands on the first page they may open)
export const COMPANY_PAGES = [
  { to: '/company', perms: ['view_company_dashboard', 'view_company_visits'] },
  { to: '/company/record', perms: ['record_visits'] },
  { to: '/company/attendance', perms: ['take_attendance'] },
  { to: '/company/services', perms: ['view_company_services', 'manage_company_services'] },
  { to: '/company/attended', perms: ['view_employees_attended', 'view_company_visits'] },
  { to: '/company/visits', perms: ['view_company_visits'] },
  { to: '/company/payments', perms: ['view_company_visits'] },
  { to: '/company/staff', perms: ['manage_company_staff'] },
]
export const EMPLOYEE_PERMISSIONS = ['use_services']

// Where a user lands after logging in
export function homeFor(user) {
  if (can(user, ...EUCL_PERMISSIONS)) return '/eucl'
  const own = user?.role_permissions ?? [] // from roles, not the super admin flag
  if (user?.company) {
    const page = COMPANY_PAGES.find((item) => item.perms.some((p) => own.includes(p)))
    if (page) return page.to
  }
  if (own.includes('use_services')) return '/my-wellness'
  return null
}

// Permission areas, in the order they are shown when editing a role
export const PERMISSION_AREAS = ['Platform', 'EUCL', 'Company', 'Employee', 'M&E']
