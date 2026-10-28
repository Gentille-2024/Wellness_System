import { jsPDF } from 'jspdf'
import { autoTable } from 'jspdf-autotable'
import { formatDate, formatMoney, formatTime } from './format.js'
import { statementRows } from './statement.js'

const GREEN = [31, 122, 85]

/**
 * Download a list of visits as a PDF report.
 *
 *   exportVisitsPdf({ title: 'Usage records', filtersText: 'From … to …', rows, columns: { company: true } })
 */
export function exportVisitsPdf({ title, filtersText, rows, columns = {}, filename }) {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' })
  const pageWidth = doc.internal.pageSize.getWidth()

  // ---- header
  doc.setFillColor(...GREEN)
  doc.rect(0, 0, pageWidth, 56, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(16)
  doc.text('EUCL Wellness Management System', 40, 34)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(10)
  doc.text(`Generated ${new Date().toLocaleString()}`, pageWidth - 40, 34, { align: 'right' })

  doc.setTextColor(21, 32, 27)
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(14)
  doc.text(title, 40, 86)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(10)
  doc.setTextColor(107, 122, 115)
  doc.text(filtersText || 'All records', 40, 104)

  // ---- table
  const head = ['Date', 'Time']
  if (columns.employee !== false) head.push('Employee', 'Department')
  if (columns.company !== false) head.push('Company')
  head.push('Service', 'Amount', 'Paid')

  const body = rows.map((visit) => {
    const row = [formatDate(visit.visit_date), formatTime(visit.visited_at)]
    if (columns.employee !== false) row.push(`${visit.employee_name} (${visit.employee_code})`, visit.department || '')
    if (columns.company !== false) row.push(visit.company_name)
    row.push(visit.service_name, formatMoney(visit.price), visit.is_paid ? 'Yes' : 'No')
    return row
  })

  const total = rows.reduce((sum, visit) => sum + Number(visit.price), 0)
  const unpaid = rows.filter((visit) => !visit.is_paid).reduce((sum, visit) => sum + Number(visit.price), 0)

  autoTable(doc, {
    startY: 120,
    head: [head],
    body,
    foot: [[{ content: `${rows.length} visit${rows.length === 1 ? '' : 's'}   ·   Total ${formatMoney(total)}   ·   Unpaid ${formatMoney(unpaid)}`, colSpan: head.length }]],
    showFoot: 'lastPage', // totals once, at the end
    styles: { fontSize: 9, cellPadding: 5 },
    headStyles: { fillColor: GREEN, textColor: 255 },
    footStyles: { fillColor: [238, 241, 239], textColor: [21, 32, 27], fontStyle: 'bold' },
    alternateRowStyles: { fillColor: [248, 250, 249] },
    margin: { left: 40, right: 40 },
    didDrawPage: () => {
      const pageHeight = doc.internal.pageSize.getHeight()
      doc.setFontSize(9)
      doc.setTextColor(107, 122, 115)
      doc.text(`Page ${doc.getNumberOfPages()}`, pageWidth - 40, pageHeight - 20, { align: 'right' })
    },
  })

  doc.save(filename || 'usage-records.pdf')
}

/**
 * Download the "employees attended" summary: one line per EUCL employee with
 * the services they used, the number of visits and the amount; totals at the end.
 */
export function exportEmployeeSummaryPdf({ title, filtersText, data, filename }) {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' })
  const pageWidth = doc.internal.pageSize.getWidth()

  doc.setFillColor(...GREEN)
  doc.rect(0, 0, pageWidth, 56, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(16)
  doc.text('EUCL Wellness Management System', 40, 34)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(10)
  doc.text(`Generated ${new Date().toLocaleString()}`, pageWidth - 40, 34, { align: 'right' })

  doc.setTextColor(21, 32, 27)
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(14)
  doc.text(title, 40, 86)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(10)
  doc.setTextColor(107, 122, 115)
  doc.text(filtersText || 'All records', 40, 104)

  autoTable(doc, {
    startY: 120,
    head: [['Employee', 'Department', 'Services used', 'Visits', 'Days', 'Amount']],
    body: data.employees.map((row) => [
      `${row.employee_name} (${row.employee_code})`,
      row.department || '',
      row.services.map((s) => `${s.service} x${s.count} (${formatMoney(s.amount)})`).join('\n'),
      row.visits,
      row.days,
      formatMoney(row.total),
    ]),
    foot: [[
      `${data.totals.employees} employee${data.totals.employees === 1 ? '' : 's'}`,
      '',
      '',
      data.totals.visits,
      '',
      formatMoney(data.totals.amount),
    ]],
    showFoot: 'lastPage',
    styles: { fontSize: 9, cellPadding: 5, valign: 'top' },
    columnStyles: { 3: { halign: 'right' }, 4: { halign: 'right' }, 5: { halign: 'right' } },
    headStyles: { fillColor: GREEN, textColor: 255 },
    footStyles: { fillColor: [238, 241, 239], textColor: [21, 32, 27], fontStyle: 'bold' },
    alternateRowStyles: { fillColor: [248, 250, 249] },
    margin: { left: 40, right: 40 },
    didDrawPage: () => {
      const pageHeight = doc.internal.pageSize.getHeight()
      doc.setFontSize(9)
      doc.setTextColor(107, 122, 115)
      doc.text(`Page ${doc.getNumberOfPages()}`, pageWidth - 40, pageHeight - 20, { align: 'right' })
    },
  })

  doc.save(filename || 'employees-attended.pdf')
}

/**
 * Download the payment statement: each EUCL employee and the amount,
 * a total per company (EUCL's statement) and the grand total.
 */
export function exportStatementPdf({ title, details, data, perCompany, filename }) {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'pt', format: 'a4' })
  const pageWidth = doc.internal.pageSize.getWidth()

  doc.setFillColor(...GREEN)
  doc.rect(0, 0, pageWidth, 56, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(15)
  doc.text('EUCL Wellness Management System', 40, 34)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9)
  doc.text(`Generated ${new Date().toLocaleString()}`, pageWidth - 40, 34, { align: 'right' })

  doc.setTextColor(21, 32, 27)
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(14)
  doc.text(title, 40, 86)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(10)
  doc.setTextColor(107, 122, 115)
  details.forEach((line, index) => doc.text(line, 40, 104 + index * 14))

  const head = [...(perCompany ? ['Company'] : []), 'Employee', 'Department', 'Visits', 'Amount']
  const amountCol = head.length - 1
  const rows = statementRows(data, { perCompany })
  const total = rows.pop()

  autoTable(doc, {
    startY: 112 + details.length * 14,
    head: [head],
    body: rows.map((row) =>
      row.kind === 'employee'
        ? [...(perCompany ? [row.company] : []), `${row.name} (${row.code})`, row.department, row.visits, formatMoney(row.amount)]
        : [{ content: row.name, colSpan: head.length - 2, styles: { fontStyle: 'bold', fillColor: [238, 241, 239] } },
           { content: row.visits, styles: { fontStyle: 'bold', fillColor: [238, 241, 239] } },
           { content: formatMoney(row.amount), styles: { fontStyle: 'bold', fillColor: [238, 241, 239] } }],
    ),
    foot: [[{ content: total.name, colSpan: head.length - 2 }, total.visits, formatMoney(total.amount)]],
    showFoot: 'lastPage',
    styles: { fontSize: 9, cellPadding: 5 },
    columnStyles: { [amountCol - 1]: { halign: 'right' }, [amountCol]: { halign: 'right' } },
    headStyles: { fillColor: GREEN, textColor: 255 },
    footStyles: { fillColor: [227, 239, 233], textColor: [21, 32, 27], fontStyle: 'bold', halign: 'right' },
    margin: { left: 40, right: 40 },
    didParseCell: (hook) => {
      // Keep the label of the total row on the left
      if (hook.section === 'foot' && hook.column.index === 0) hook.cell.styles.halign = 'left'
      // Number headings line up with their numbers
      if (hook.section === 'head' && hook.column.index >= amountCol - 1) hook.cell.styles.halign = 'right'
    },
    didDrawPage: () => {
      const pageHeight = doc.internal.pageSize.getHeight()
      doc.setFontSize(9)
      doc.setTextColor(107, 122, 115)
      doc.text(`Page ${doc.getNumberOfPages()}`, pageWidth - 40, pageHeight - 20, { align: 'right' })
    },
  })

  doc.save(filename)
}
