import { can } from './auth/access'

// Every menu link and the permission(s) that show it.
// A user sees a link if they have ANY of its permissions.
const SECTIONS = [
  {
    section: 'EUCL',
    items: [
      { to: '/eucl', label: 'Dashboard', icon: 'dashboard', end: true, perms: ['manage_companies', 'manage_users', 'view_all_visits', 'manage_payments', 'manage_employees'] },
      { to: '/eucl/companies', label: 'Companies', icon: 'building', perms: ['manage_companies'] },
      { to: '/eucl/employees', label: 'EUCL employees', icon: 'users', perms: ['manage_employees'] },
      { to: '/eucl/visits', label: 'Usage records', icon: 'activity', perms: ['view_all_visits', 'manage_payments'] },
      { to: '/eucl/payments', label: 'Payments', icon: 'card', perms: ['manage_payments'] },
      { to: '/eucl/users', label: 'Users & roles', icon: 'shield', perms: ['manage_users'] },
    ],
  },
  {
    section: 'My company',
    needsCompany: true,
    items: [
      { to: '/company', label: 'Dashboard', icon: 'dashboard', end: true, perms: ['view_company_dashboard', 'view_company_visits'] },
      { to: '/company/record', label: 'Record visits', icon: 'checkin', perms: ['record_visits'] },
      { to: '/company/attendance', label: 'Employees attendance', icon: 'calendar', perms: ['take_attendance'] },
      { to: '/company/services', label: 'Services & prices', icon: 'sparkles', perms: ['view_company_services', 'manage_company_services'] },
      { to: '/company/attended', label: 'Employees attended', icon: 'users', perms: ['view_employees_attended', 'view_company_visits'] },
      { to: '/company/visits', label: 'Visits', icon: 'activity', perms: ['view_company_visits'] },
      { to: '/company/payments', label: 'Payments', icon: 'card', perms: ['view_company_visits'] },
      { to: '/company/staff', label: 'Staff', icon: 'shield', perms: ['manage_company_staff'] },
    ],
  },
  {
    section: 'My wellness',
    items: [
      { to: '/my-wellness', label: 'Overview', icon: 'dashboard', end: true, perms: ['use_services'] },
      { to: '/my-wellness/places', label: 'Places & services', icon: 'map', perms: ['use_services'] },
      { to: '/my-wellness/visits', label: 'My visits', icon: 'clock', perms: ['use_services'] },
    ],
  },
]

const ACCOUNT = {
  section: 'Account',
  items: [{ to: '/account', label: 'My account', icon: 'key' }],
}

// The menu for this user: only the links their permissions allow
export function navFor(user) {
  const sections = SECTIONS.filter((section) => !section.needsCompany || user.company)
    .map((section) => ({
      ...section,
      // The super admin has every permission, but company/employee pages
      // only make sense for real company staff and employees
      items: section.items.filter((item) =>
        section.section === 'EUCL' ? can(user, ...item.perms) : item.perms.some((perm) => user.role_permissions.includes(perm)),
      ),
    }))
    .filter((section) => section.items.length > 0)
  return [...sections, ACCOUNT]
}
