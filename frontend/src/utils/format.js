// "2026-09-24T13:53:27+02:00" -> "13:53"
export function formatTime(isoDateTime) {
  return new Date(isoDateTime).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

// "2026-09-24T13:53:27+02:00" -> "24 Sep 2026, 13:53"
export function formatDateTime(isoDateTime) {
  if (!isoDateTime) return '—'
  return new Date(isoDateTime).toLocaleString([], {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// A Date as "YYYY-MM-DD" (the format the API and <input type="date"> use)
export function toISODate(date) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

// Today's date as "YYYY-MM-DD"
export function todayISO() {
  return toISODate(new Date())
}

// The date `days` days ago as "YYYY-MM-DD"
export function daysAgoISO(days) {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return toISODate(date)
}

// Build a Date from "YYYY-MM-DD" without the browser shifting it by a time zone
function parseISODate(isoDate) {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(year, month - 1, day)
}

// "2026-12-24" -> "24 Dec 2026"
export function formatDate(isoDate) {
  if (!isoDate) return '—'
  return parseISODate(isoDate).toLocaleDateString([], {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

// "2026-09-24" -> "Thu 24"
export function formatShortDay(isoDate) {
  return parseISODate(isoDate).toLocaleDateString([], { weekday: 'short', day: 'numeric' })
}

// "2026-09" -> "September 2026"
export function formatMonth(yearMonth) {
  return parseISODate(`${yearMonth}-01`).toLocaleDateString([], {
    month: 'long',
    year: 'numeric',
  })
}

// 15000 or "15000.00" -> "RWF 15,000"
const rwf = new Intl.NumberFormat('en-RW', { style: 'currency', currency: 'RWF', maximumFractionDigits: 0 })
export function formatMoney(amount) {
  return rwf.format(Number(amount ?? 0))
}

// The first day of the current month as "YYYY-MM-DD"
export function monthStartISO() {
  return todayISO().slice(0, 8) + '01'
}

// Initials for avatars: "John Doe" -> "JD"
export function initials(name) {
  return (name || '?')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')
}
