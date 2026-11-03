// What a user may do is decided by their PERMISSIONS (which come from their
// roles). Roles can be created in the app, so screens never check role names.

// Does this user have at least one of these permissions?  can(user, 'record_visits')
// Super admins too: their permissions come from the Super admin role
export function can(user, ...permissions) {
  if (!user) return false
  return permissions.some((permission) => user.permissions?.includes(permission))
}

// The three areas of the app and the permissions that open them
export const EUCL_PERMISSIONS = ['manage_companies', 'manage_users', 'view_all_visits', 'manage_payments', 'manage_employees', 'import_employees', 'view_all_employees_attended', 'view_feedback', 'view_price_changes']
// The EUCL dashboard is for EUCL management; HR (manage_employees only) just gets EUCL employees
export const EUCL_DASHBOARD_PERMISSIONS = ['manage_companies', 'manage_users', 'view_all_visits', 'manage_payments']
export const COMPANY_PERMISSIONS = [
  'view_company_dashboard',
  'record_visits',
  'take_attendance',
  'view_company_services',
  'edit_service_prices',
  'view_employees_attended',
  'view_company_visits',
  'manage_company_services',
  'manage_company_staff',
  'view_company_feedback',
]

// Company pages in menu order, and the permissions that open each one
// (a company user lands on the first page they may open)
export const COMPANY_PAGES = [
  { to: '/company', perms: ['view_company_dashboard', 'view_company_visits'] },
  { to: '/company/record', perms: ['record_visits'] },
  { to: '/company/attendance', perms: ['take_attendance'] },
  { to: '/company/services', perms: ['view_company_services', 'manage_company_services', 'edit_service_prices'] },
  { to: '/company/attended', perms: ['view_employees_attended', 'view_company_visits'] },
  { to: '/company/visits', perms: ['view_company_visits'] },
  { to: '/company/payments', perms: ['view_company_visits'] },
  { to: '/company/staff', perms: ['manage_company_staff'] },
  { to: '/company/feedback', perms: ['view_company_feedback'] },
]
// EUCL pages after the dashboard, in menu order (someone without the
// dashboard lands on the first one they may open)
export const EUCL_PAGES = [
  { to: '/eucl/companies', perms: ['manage_companies'] },
  { to: '/eucl/employees', perms: ['manage_employees', 'import_employees'] },
  { to: '/eucl/attended', perms: ['view_all_employees_attended'] },
  { to: '/eucl/visits', perms: ['view_all_visits', 'manage_payments'] },
  { to: '/eucl/payments', perms: ['manage_payments'] },
  { to: '/eucl/price-changes', perms: ['view_price_changes'] },
  { to: '/eucl/feedback', perms: ['view_feedback'] },
  { to: '/eucl/users', perms: ['manage_users'] },
]
// My wellness: one permission per page, in menu order
export const EMPLOYEE_PAGES = [
  { to: '/my-wellness', perms: ['view_my_overview'] },
  { to: '/my-wellness/places', perms: ['view_places'] },
  { to: '/my-wellness/visits', perms: ['view_my_services'] },
]
export const EMPLOYEE_PERMISSIONS = ['view_my_overview', 'view_places', 'view_my_services']

// M&E officers (and anyone else whose only work pages are in the M&E tool)
// go straight to the M&E tool, signed in as themselves. Someone with an EUCL
// or company page here (super admin, HR, boss...) starts here instead.
const ME_TOOL_PERMISSIONS = ['view_me_dashboards', 'manage_me_targets']
export function meToolIsHome(user) {
  if (!can(user, ...ME_TOOL_PERMISSIONS)) return false
  if (can(user, ...EUCL_DASHBOARD_PERMISSIONS)) return false
  if (EUCL_PAGES.some((page) => can(user, ...page.perms))) return false
  const own = user?.role_permissions ?? []
  if (user?.company && COMPANY_PAGES.some((page) => page.perms.some((p) => own.includes(p)))) return false
  return true
}

// Where a user lands after logging in
export function homeFor(user) {
  if (can(user, ...EUCL_DASHBOARD_PERMISSIONS)) return '/eucl'
  const own = user?.role_permissions ?? [] // from roles, not the super admin flag
  if (user?.company) {
    const page = COMPANY_PAGES.find((item) => item.perms.some((p) => own.includes(p)))
    if (page) return page.to
  }
  const employeePage = EMPLOYEE_PAGES.find((item) => item.perms.some((p) => own.includes(p)))
  if (employeePage) return employeePage.to
  const euclPage = EUCL_PAGES.find((item) => can(user, ...item.perms))
  if (euclPage) return euclPage.to
  return null
}

// Permission areas, in the order they are shown when editing a role
export const PERMISSION_AREAS = ['Platform', 'EUCL', 'Company', 'Employee', 'M&E']

// Permissions grouped by area, in that order; areas the super admin added come last
export function groupByArea(permissions = []) {
  const areas = [...PERMISSION_AREAS, ...new Set(permissions.map((p) => p.area).filter((area) => !PERMISSION_AREAS.includes(area)))]
  return areas.map((area) => ({ area, items: permissions.filter((p) => p.area === area) })).filter((group) => group.items.length)
}

// The built-in roles first, in this order, then the others by name
const ROLE_ORDER = ['SUPER_ADMIN', 'COMPANY_BOSS', 'COMPANY_RECEPTIONIST', 'EUCL_HR', 'ME_OFFICER', 'EMPLOYEE']
export function sortRoles(roles = []) {
  const rank = (role) => (ROLE_ORDER.includes(role.code) ? ROLE_ORDER.indexOf(role.code) : ROLE_ORDER.length)
  return [...roles].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name))
}
