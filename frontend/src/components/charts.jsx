import { useState } from 'react'
import { formatDate, formatShortDay } from '../utils/format'
import { EmptyState } from './ui'

// Check-ins per day as vertical bars (one series, so one colour and no legend).
// Hovering a bar shows its exact value; a hidden table serves screen readers.
export function DailyChart({ days }) {
  const [hovered, setHovered] = useState(null)
  const max = Math.max(1, ...days.map((day) => day.count))
  const total = days.reduce((sum, day) => sum + day.count, 0)

  if (total === 0) {
    return (
      <EmptyState icon="activity" title="No check-ins in the last 14 days">
        Visits will appear here as the reception records them.
      </EmptyState>
    )
  }

  return (
    <div className="bar-chart">
      <div className="bar-chart-scale">
        <span>{max}</span>
        <span>0</span>
      </div>
      <div className="bar-chart-plot" onMouseLeave={() => setHovered(null)}>
        {days.map((day, index) => (
          <div
            key={day.date}
            className="bar-slot"
            onMouseEnter={() => setHovered(index)}
            onFocus={() => setHovered(index)}
            tabIndex={0}
            aria-label={`${formatDate(day.date)}: ${day.count} check-ins`}
          >
            <div
              className={hovered === index ? 'bar hovered' : 'bar'}
              style={{ height: `${(day.count / max) * 100}%` }}
            />
            {hovered === index && (
              <div className="chart-tooltip">
                <strong>{day.count}</strong> check-in{day.count === 1 ? '' : 's'}
                <span>{formatDate(day.date)}</span>
              </div>
            )}
            <span className="bar-label">{index % 2 === 0 || index === days.length - 1 ? formatShortDay(day.date) : ''}</span>
          </div>
        ))}
      </div>

      <table className="sr-only">
        <caption>Check-ins per day</caption>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <th scope="row">{formatDate(day.date)}</th>
              <td>{day.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Visits per service as labelled horizontal bars
export function ServiceBreakdown({ rows }) {
  const total = rows.reduce((sum, row) => sum + row.count, 0)
  const max = Math.max(1, ...rows.map((row) => row.count))

  if (total === 0) {
    return <EmptyState icon="sparkles" title="No visits yet" />
  }

  return (
    <ul className="breakdown">
      {rows.map((row) => (
        <li key={row.service}>
          <div className="breakdown-head">
            <span>{row.service}</span>
            <span className="breakdown-value">
              {row.count} <span className="muted">· {Math.round((row.count / total) * 100)}%</span>
            </span>
          </div>
          <div className="breakdown-track">
            <div className="breakdown-bar" style={{ width: `${(row.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}
