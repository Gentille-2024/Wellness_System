import { Badge } from './ui'

// Open / Deactivated / Deleted
export default function CompanyStatus({ company }) {
  if (company.is_deleted) return <Badge tone="danger">Deleted</Badge>
  if (!company.is_active) return <Badge tone="warning">Deactivated</Badge>
  return <Badge tone="success">Open</Badge>
}
