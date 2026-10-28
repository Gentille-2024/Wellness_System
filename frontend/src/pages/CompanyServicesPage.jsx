import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import ServicesManager from '../components/ServicesManager'
import { Alert, PageHeader } from '../components/ui'

// Company boss: the services the company offers EUCL employees, and their prices.
// Receptionists see the same list without the edit buttons.
export default function CompanyServicesPage() {
  const { user } = useAuth()
  const [notice, setNotice] = useState('')
  const canEdit = user.role_permissions.includes('manage_company_services')

  return (
    <>
      <PageHeader
        title="Services & prices"
        subtitle={canEdit ? 'What EUCL employees can use here. EUCL pays the price each time.' : 'What EUCL employees can use here.'}
      />
      <Alert type="success">{notice}</Alert>
      <ServicesManager companyId={user.company?.id} canEdit={canEdit} onNotice={setNotice} />
    </>
  )
}
