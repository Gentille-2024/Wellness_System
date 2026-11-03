import { Navigate, Outlet, Route, Routes } from 'react-router'
import { useAuth } from './auth/AuthContext'
import { useEffect, useRef, useState } from 'react'
import { can, COMPANY_PERMISSIONS, EMPLOYEE_PERMISSIONS, EUCL_DASHBOARD_PERMISSIONS, EUCL_PERMISSIONS, homeFor, meToolIsHome } from './auth/access'
import { errorMessage } from './api/client'
import { meToolSignInUrl } from './api/meTool'
import { ME_PERMISSIONS, ME_TOOL_URL } from './navigation'
import AppLayout from './components/AppLayout'
import ProtectedRoute from './components/ProtectedRoute'
import { EmptyState, Loading } from './components/ui'
import AccountPage from './pages/AccountPage'
import CompaniesPage from './pages/CompaniesPage'
import CompanyActivityPage from './pages/CompanyActivityPage'
import AttendancePage from './pages/AttendancePage'
import CompanyDashboard from './pages/CompanyDashboard'
import EmployeesAttendedPage from './pages/EmployeesAttendedPage'
import CompanyDetailPage from './pages/CompanyDetailPage'
import CompanyServicesPage from './pages/CompanyServicesPage'
import EmployeeDetailPage from './pages/EmployeeDetailPage'
import EmployeeHomePage from './pages/EmployeeHomePage'
import EmployeesPage from './pages/EmployeesPage'
import EuclDashboard from './pages/EuclDashboard'
import FeedbackPage from './pages/FeedbackPage'
import FirstLoginPage from './pages/FirstLoginPage'
import LoginPage from './pages/LoginPage'
import PaymentsPage from './pages/PaymentsPage'
import PlaceDetailPage from './pages/PlaceDetailPage'
import PlacesPage from './pages/PlacesPage'
import PriceChangesPage from './pages/PriceChangesPage'
import RecordVisitsPage from './pages/RecordVisitsPage'
import UsersPage from './pages/UsersPage'
import VisitsPage from './pages/VisitsPage'

// "/" sends each user to the right home for their permissions
function HomeRedirect() {
  const { user } = useAuth()
  if (meToolIsHome(user)) return <MeToolRedirect />
  const target = homeFor(user)
  if (!target) {
    // The M&E tool is a separate website: its link is in the menu
    if (can(user, ...ME_PERMISSIONS)) {
      return (
        <EmptyState icon="activity" title="Your pages are in the M&E tool">
          Open the <a href={ME_TOOL_URL}>M&amp;E tool</a> (also in the menu).
        </EmptyState>
      )
    }
    return (
      <EmptyState icon="shield" title="No access yet">
        {user?.permissions?.length
          ? 'Your role has no permission that opens a page here. Ask the EUCL administrator to switch one on for your role.'
          : 'Your login has no role. Ask the EUCL administrator to give you one.'}
      </EmptyState>
    )
  }
  return <Navigate to={target} replace />
}

// An M&E officer's home is the M&E tool: go there, signed in as themselves
function MeToolRedirect() {
  const [error, setError] = useState('')
  const started = useRef(false) // once, also in React's development double run

  useEffect(() => {
    if (started.current) return
    started.current = true
    meToolSignInUrl()
      .then((url) => window.location.replace(url))
      .catch((err) => setError(errorMessage(err)))
  }, [])

  if (!error) return <Loading text="Opening the M&E tool…" />
  return (
    <EmptyState icon="activity" title="The M&E tool could not be opened">
      {error} Try the <a href={ME_TOOL_URL}>M&amp;E tool</a> sign-in page, or use the menu.
    </EmptyState>
  )
}

// A page (or group of pages) that needs one of these permissions
function Allow({ perms, exact, needsCompany, children }) {
  return (
    <ProtectedRoute perms={perms} exact={exact} needsCompany={needsCompany}>
      {children ?? <Outlet />}
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/first-login" element={<FirstLoginPage />} />

      {/* Everything inside here requires login and uses the sidebar layout */}
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<HomeRedirect />} />
        <Route path="account" element={<AccountPage />} />

        {/* EUCL: super admin, HR, finance… depending on their roles */}
        <Route path="eucl" element={<Allow perms={EUCL_PERMISSIONS} />}>
          <Route index element={<Allow perms={EUCL_DASHBOARD_PERMISSIONS}><EuclDashboard /></Allow>} />
          <Route path="companies" element={<Allow perms={['manage_companies']} />}>
            <Route index element={<CompaniesPage />} />
            <Route path=":companyId" element={<CompanyDetailPage />} />
          </Route>
          <Route path="employees">
            <Route index element={<Allow perms={['manage_employees', 'import_employees']}><EmployeesPage /></Allow>} />
            <Route path=":employeeId" element={<Allow perms={['manage_employees']}><EmployeeDetailPage /></Allow>} />
          </Route>
          <Route path="attended" element={<Allow perms={['view_all_employees_attended']}><EmployeesAttendedPage scope="eucl" /></Allow>} />
          <Route path="visits" element={<Allow perms={['view_all_visits', 'manage_payments']}><VisitsPage scope="eucl" /></Allow>} />
          <Route path="activity/:companyId" element={<Allow perms={['view_all_visits', 'manage_payments']}><CompanyActivityPage /></Allow>} />
          <Route path="payments" element={<Allow perms={['manage_payments']}><PaymentsPage scope="eucl" /></Allow>} />
          <Route path="feedback" element={<Allow perms={['view_feedback']}><FeedbackPage scope="eucl" /></Allow>} />
          <Route path="price-changes" element={<Allow perms={['view_price_changes']}><PriceChangesPage /></Allow>} />
          <Route path="users" element={<Allow perms={['manage_users']}><UsersPage scope="platform" /></Allow>} />
        </Route>

        {/* A service provider's staff: boss, receptionist… */}
        <Route path="company" element={<Allow perms={COMPANY_PERMISSIONS} exact needsCompany />}>
          <Route index element={<Allow perms={['view_company_dashboard', 'view_company_visits']} exact><CompanyDashboard /></Allow>} />
          <Route path="record" element={<Allow perms={['record_visits']} exact><RecordVisitsPage /></Allow>} />
          <Route path="attendance" element={<Allow perms={['take_attendance']} exact><AttendancePage /></Allow>} />
          <Route path="services" element={<Allow perms={['view_company_services', 'manage_company_services', 'edit_service_prices']} exact><CompanyServicesPage /></Allow>} />
          <Route path="attended" element={<Allow perms={['view_employees_attended', 'view_company_visits']} exact><EmployeesAttendedPage /></Allow>} />
          <Route path="visits" element={<Allow perms={['view_company_visits']} exact><VisitsPage scope="company" /></Allow>} />
          <Route path="payments" element={<Allow perms={['view_company_visits']} exact><PaymentsPage scope="company" /></Allow>} />
          <Route path="staff" element={<Allow perms={['manage_company_staff']} exact><UsersPage scope="company" /></Allow>} />
          <Route path="feedback" element={<Allow perms={['view_company_feedback']} exact><FeedbackPage scope="company" /></Allow>} />
        </Route>

        {/* EUCL employees */}
        <Route path="my-wellness" element={<Allow perms={EMPLOYEE_PERMISSIONS} exact />}>
          <Route index element={<Allow perms={['view_my_overview']} exact><EmployeeHomePage /></Allow>} />
          <Route path="places" element={<Allow perms={['view_places']} exact><PlacesPage /></Allow>} />
          <Route path="places/:placeId" element={<Allow perms={['view_places']} exact><PlaceDetailPage /></Allow>} />
          <Route path="visits" element={<Allow perms={['view_my_services']} exact><VisitsPage scope="mine" /></Allow>} />
        </Route>
      </Route>

      {/* Unknown address: go home */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
