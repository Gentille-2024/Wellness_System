import { Navigate, Outlet, Route, Routes } from 'react-router'
import { useAuth } from './auth/AuthContext'
import { COMPANY_PERMISSIONS, EUCL_PERMISSIONS, homeFor } from './auth/access'
import AppLayout from './components/AppLayout'
import ProtectedRoute from './components/ProtectedRoute'
import { EmptyState } from './components/ui'
import AccountPage from './pages/AccountPage'
import CompaniesPage from './pages/CompaniesPage'
import AttendancePage from './pages/AttendancePage'
import CompanyDashboard from './pages/CompanyDashboard'
import EmployeesAttendedPage from './pages/EmployeesAttendedPage'
import CompanyDetailPage from './pages/CompanyDetailPage'
import CompanyServicesPage from './pages/CompanyServicesPage'
import EmployeeDetailPage from './pages/EmployeeDetailPage'
import EmployeeHomePage from './pages/EmployeeHomePage'
import EmployeesPage from './pages/EmployeesPage'
import EuclDashboard from './pages/EuclDashboard'
import LoginPage from './pages/LoginPage'
import PaymentsPage from './pages/PaymentsPage'
import PlaceDetailPage from './pages/PlaceDetailPage'
import PlacesPage from './pages/PlacesPage'
import RecordVisitsPage from './pages/RecordVisitsPage'
import UsersPage from './pages/UsersPage'
import VisitsPage from './pages/VisitsPage'

// "/" sends each user to the right home for their permissions
function HomeRedirect() {
  const { user } = useAuth()
  const target = homeFor(user)
  if (!target) {
    return (
      <EmptyState icon="shield" title="No access yet">
        Your login has no role. Ask the EUCL administrator to give you one.
      </EmptyState>
    )
  }
  return <Navigate to={target} replace />
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
          <Route index element={<EuclDashboard />} />
          <Route path="companies" element={<Allow perms={['manage_companies']} />}>
            <Route index element={<CompaniesPage />} />
            <Route path=":companyId" element={<CompanyDetailPage />} />
          </Route>
          <Route path="employees" element={<Allow perms={['manage_employees']} />}>
            <Route index element={<EmployeesPage />} />
            <Route path=":employeeId" element={<EmployeeDetailPage />} />
          </Route>
          <Route path="visits" element={<Allow perms={['view_all_visits', 'manage_payments']}><VisitsPage scope="eucl" /></Allow>} />
          <Route path="payments" element={<Allow perms={['manage_payments']}><PaymentsPage scope="eucl" /></Allow>} />
          <Route path="users" element={<Allow perms={['manage_users']}><UsersPage scope="platform" /></Allow>} />
        </Route>

        {/* A service provider's staff: boss, receptionist… */}
        <Route path="company" element={<Allow perms={COMPANY_PERMISSIONS} exact needsCompany />}>
          <Route index element={<Allow perms={['view_company_dashboard', 'view_company_visits']} exact><CompanyDashboard /></Allow>} />
          <Route path="record" element={<Allow perms={['record_visits']} exact><RecordVisitsPage /></Allow>} />
          <Route path="attendance" element={<Allow perms={['take_attendance']} exact><AttendancePage /></Allow>} />
          <Route path="services" element={<Allow perms={['view_company_services', 'manage_company_services']} exact><CompanyServicesPage /></Allow>} />
          <Route path="attended" element={<Allow perms={['view_employees_attended', 'view_company_visits']} exact><EmployeesAttendedPage /></Allow>} />
          <Route path="visits" element={<Allow perms={['view_company_visits']} exact><VisitsPage scope="company" /></Allow>} />
          <Route path="payments" element={<Allow perms={['view_company_visits']} exact><PaymentsPage scope="company" /></Allow>} />
          <Route path="staff" element={<Allow perms={['manage_company_staff']} exact><UsersPage scope="company" /></Allow>} />
        </Route>

        {/* EUCL employees */}
        <Route path="my-wellness" element={<Allow perms={['use_services']} exact />}>
          <Route index element={<EmployeeHomePage />} />
          <Route path="places" element={<PlacesPage />} />
          <Route path="places/:placeId" element={<PlaceDetailPage />} />
          <Route path="visits" element={<VisitsPage scope="mine" />} />
        </Route>
      </Route>

      {/* Unknown address: go home */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
