/**
 * Payment statement exports: the EUCL employees who used services, the amount
 * for each, a total per company (EUCL only) and the grand total.
 * Both exports are built from the same rows, from GET /api/payments/statement/.
 *
 * Each row: { kind: 'employee' | 'subtotal' | 'total', company, name, code, department, visits, amount }
 */
export function statementRows(data, { perCompany }) {
  const rows = []
  for (const company of data.companies) {
    for (const employee of company.employees) {
      rows.push({
        kind: 'employee',
        company: company.company_name,
        name: employee.employee_name || employee.employee_code,
        code: employee.employee_code,
        department: employee.department || '',
        visits: employee.visits,
        amount: Number(employee.amount),
      })
    }
    if (perCompany) {
      rows.push({
        kind: 'subtotal',
        company: company.company_name,
        name: `${company.company_name} total (${plural(company.employee_count, 'employee')})`,
        visits: company.visits,
        amount: Number(company.amount),
      })
    }
  }
  const totals = data.totals
  rows.push({
    kind: 'total',
    name: perCompany
      ? `Total (${plural(totals.employees, 'employee')}, ${plural(totals.companies, 'company', 'companies')})`
      : `Total (${plural(totals.employees, 'employee')})`,
    visits: totals.visits,
    amount: Number(totals.amount),
  })
  return rows
}

export function plural(count, one, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`
}

// Download the statement as a real Excel file (.xlsx)
export async function exportStatementExcel({ title, details, data, perCompany, filename }) {
  // Loaded only when someone exports
  const { default: writeXlsxFile } = await import('write-excel-file/browser')

  const header = (value) => ({ value, fontWeight: 'bold', backgroundColor: '#1F7A55', textColor: '#FFFFFF' })
  const columns = [...(perCompany ? ['Company'] : []), 'Employee', 'Employee ID', 'Department', 'Visits', 'Amount (RWF)']
  const money = { type: Number, format: '#,##0' }

  const sheet = [
    [{ value: 'EUCL Wellness Management System', fontWeight: 'bold', fontSize: 14 }],
    [{ value: title, fontWeight: 'bold' }],
    ...details.map((line) => [line]),
    [`Generated ${new Date().toLocaleString()}`],
    [],
    columns.map(header),
  ]

  for (const row of statementRows(data, { perCompany })) {
    if (row.kind === 'employee') {
      sheet.push([
        ...(perCompany ? [row.company] : []),
        row.name,
        row.code,
        row.department,
        { value: row.visits, type: Number },
        { ...money, value: row.amount },
      ])
    } else {
      const strong = row.kind === 'total'
        ? { fontWeight: 'bold', backgroundColor: '#E3EFE9', topBorderStyle: 'thin' }
        : { fontWeight: 'bold', backgroundColor: '#F3F6F4' }
      sheet.push([
        { value: row.name, ...strong },
        ...Array(columns.length - 3).fill({ value: null, ...strong }),
        { value: row.visits, type: Number, ...strong },
        { ...money, value: row.amount, ...strong },
      ])
    }
  }

  await writeXlsxFile(sheet, {
    sheet: 'Payments',
    columns: [...(perCompany ? [{ width: 26 }] : []), { width: 28 }, { width: 14 }, { width: 18 }, { width: 10 }, { width: 16 }],
  }).toFile(filename)
}

// "Employees attended" as Excel: each employee, the services they used,
// visits, days and amount, then the total for all employees
export async function exportEmployeeSummaryExcel({ title, details, data, filename }) {
  const { default: writeXlsxFile } = await import('write-excel-file/browser')

  const header = (value) => ({ value, fontWeight: 'bold', backgroundColor: '#1F7A55', textColor: '#FFFFFF' })
  const strong = { fontWeight: 'bold', backgroundColor: '#E3EFE9', topBorderStyle: 'thin' }
  const money = { type: Number, format: '#,##0' }

  const sheet = [
    [{ value: 'EUCL Wellness Management System', fontWeight: 'bold', fontSize: 14 }],
    [{ value: title, fontWeight: 'bold' }],
    ...details.map((line) => [line]),
    [`Generated ${new Date().toLocaleString()}`],
    [],
    ['Employee', 'Employee ID', 'Department', 'Services used', 'Visits', 'Days', 'Amount (RWF)'].map(header),
  ]

  for (const row of data.employees) {
    sheet.push([
      row.employee_name || row.employee_code,
      row.employee_code,
      row.department || '',
      { value: row.services.map((s) => `${s.service} ×${s.count} (${Number(s.amount).toLocaleString()} RWF)`).join('\n'), wrap: true },
      { value: row.visits, type: Number },
      { value: row.days, type: Number },
      { ...money, value: Number(row.total) },
    ])
  }

  sheet.push([
    { value: `Total (${plural(data.totals.employees, 'employee')})`, ...strong },
    { value: null, ...strong },
    { value: null, ...strong },
    { value: null, ...strong },
    { value: data.totals.visits, type: Number, ...strong },
    { value: null, ...strong },
    { ...money, value: Number(data.totals.amount), ...strong },
  ])

  await writeXlsxFile(sheet, {
    sheet: 'Employees attended',
    columns: [{ width: 26 }, { width: 13 }, { width: 16 }, { width: 46 }, { width: 9 }, { width: 8 }, { width: 15 }],
  }).toFile(filename)
}
