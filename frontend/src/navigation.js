import { can } from './auth/access'

// Every menu link and the permission(s) that show it.
// A user sees a link if they have ANY of its permissions.
const SECTIONS = [
  {
    section: 'EUCL',
    items: [
      { to: '/eucl', label: 'Dashboard', icon: 'dashboard', end: true, perms: ['manage_companies', 'manage_users', 'view_all_visits', 'manage_payments'] },
      { to: '/eucl/companies', label: 'Companies', icon: 'building', perms: ['manage_companies'] },
      { to: '/eucl/employees', label: 'EUCL employees', icon: 'users', perms: ['manage_employees', 'import_employees'] },
      { to: '/eucl/attended', label: 'Employees attended', icon: 'checkin', perms: ['view_all_employees_attended'] },
      { to: '/eucl/visits', label: 'Usage records', icon: 'activity', perms: ['view_all_visits', 'manage_payments'] },
      { to: '/eucl/payments', label: 'Payments', icon: 'card', perms: ['manage_payments'] },
      { to: '/eucl/price-changes', label: 'Price changes', icon: 'money', perms: ['view_price_changes'] },
      { to: '/eucl/feedback', label: 'Feedback', icon: 'mail', perms: ['view_feedback'] },
      { to: '/eucl/users', label: 'Users & roles', icon: 'shield', perms: ['manage_users'] },
    ],
  },
  {
    section: 'My company',
    needsCompany: true,
    items: [
      { to: '/company', label: 'Dashboard', icon: 'dashboard', end: true, perms: ['view_company_dashboard', 'view_company_visits'] },
      { to: '/company/record', label: 'Record services', icon: 'checkin', perms: ['record_visits'] },
      { to: '/company/attendance', label: 'Employees attendance', icon: 'calendar', perms: ['take_attendance'] },
      { to: '/company/services', label: 'Services & prices', icon: 'sparkles', perms: ['view_company_services', 'manage_company_services', 'edit_service_prices'] },
      { to: '/company/attended', label: 'Employees attended', icon: 'users', perms: ['view_employees_attended', 'view_company_visits'] },
      { to: '/company/visits', label: 'Services', icon: 'activity', perms: ['view_company_visits'] },
      { to: '/company/payments', label: 'Payments', icon: 'card', perms: ['view_company_visits'] },
      { to: '/company/feedback', label: 'Feedback', icon: 'mail', perms: ['view_company_feedback'] },
      { to: '/company/staff', label: 'Staff', icon: 'shield', perms: ['manage_company_staff'] },
    ],
  },
  {
    section: 'My wellness',
    items: [
      { to: '/my-wellness', label: 'Overview', icon: 'dashboard', end: true, perms: ['view_my_overview'] },
      { to: '/my-wellness/places', label: 'Places & services', icon: 'map', perms: ['view_places'] },
      { to: '/my-wellness/visits', label: 'My services', icon: 'clock', perms: ['view_my_services'] },
    ],
  },
]

// The M&E tool is a separate website; its address can be set in frontend/.env
// (VITE_ME_URL=http://…). M&E permissions are used there, not on these pages.
export const ME_TOOL_URL = import.meta.env.VITE_ME_URL || 'http://localhost:8100'
export const ME_PERMISSIONS = ['view_me_dashboards', 'manage_me_targets']

const ACCOUNT = {
  section: 'Account',
  items: [{ to: '/account', label: 'My account', icon: 'key' }],
}

// The menu for this user: only the links their permissions allow
export function navFor(user) {
  const sections = SECTIONS.filter((section) => !section.needsCompany || user.company)
    .map((section) => ({
      ...section,
      // Not linked to a company: these are the pages of the company they chose
      section: section.needsCompany && user.acting_company ? 'Company pages' : section.section,
      // The super admin has every permission, but company/employee pages
      // only make sense for real company staff and employees
      items: section.items.filter((item) =>
        section.section === 'EUCL' ? can(user, ...item.perms) : item.perms.some((perm) => user.role_permissions.includes(perm)),
      ),
    }))
    .filter((section) => section.items.length > 0)
  const me = can(user, ...ME_PERMISSIONS)
    ? [{ section: 'M&E', items: [{ href: ME_TOOL_URL, label: 'M&E tool', icon: 'activity' }] }]
    : []
  return [...sections, ...me, ACCOUNT]
}
