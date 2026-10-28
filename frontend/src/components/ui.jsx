import { useEffect, useRef, useState } from 'react'
import { initials } from '../utils/format'
import Icon from './Icon'

// Small building blocks used by every page, so all screens look the same.

export function PageHeader({ title, subtitle, actions, back }) {
  return (
    <header className="page-header">
      <div>
        {back}
        <h1>{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}

export function StatCard({ label, value, hint, icon, tone = 'primary' }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon tone-${tone}`}>
        <Icon name={icon} size={20} />
      </div>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value ?? '—'}</div>
        {hint && <div className="stat-hint">{hint}</div>}
      </div>
    </div>
  )
}

export function Card({ title, subtitle, actions, children, flush = false }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="card-header">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </div>
      )}
      <div className={flush ? 'card-body flush' : 'card-body'}>{children}</div>
    </section>
  )
}

export function Badge({ tone = 'neutral', children }) {
  return <span className={`badge tone-${tone}`}>{children}</span>
}

export function Alert({ type = 'error', children }) {
  if (!children) return null
  return (
    <div className={`alert alert-${type}`} role={type === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}

export function EmptyState({ icon = 'sparkles', title, children }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon name={icon} size={22} />
      </div>
      <div className="empty-title">{title}</div>
      {children && <div className="empty-text">{children}</div>}
    </div>
  )
}

export function Loading({ text = 'Loading…' }) {
  return (
    <div className="loading">
      <span className="spinner" aria-hidden="true" />
      {text}
    </div>
  )
}

// A labelled input with an optional error message under it.
// Every extra prop (name, value, type, required…) goes to <input>.
export function Field({ label, error, hint, className = '', ...inputProps }) {
  return (
    <label className={`field ${className}`}>
      <span className="field-label">
        {label}
        {inputProps.required && <span className="required">*</span>}
      </span>
      <input aria-invalid={Boolean(error)} {...inputProps} />
      {error ? <span className="field-error">{error}</span> : hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

export function SelectField({ label, error, hint, children, className = '', ...selectProps }) {
  return (
    <label className={`field ${className}`}>
      <span className="field-label">
        {label}
        {selectProps.required && <span className="required">*</span>}
      </span>
      <select aria-invalid={Boolean(error)} {...selectProps}>
        {children}
      </select>
      {error ? <span className="field-error">{error}</span> : hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

export function TextAreaField({ label, error, className = '', ...textareaProps }) {
  return (
    <label className={`field ${className}`}>
      <span className="field-label">{label}</span>
      <textarea rows={3} aria-invalid={Boolean(error)} {...textareaProps} />
      {error && <span className="field-error">{error}</span>}
    </label>
  )
}

export function SearchInput({ value, onChange, placeholder = 'Search…', autoFocus = false }) {
  return (
    <div className="search-input">
      <Icon name="search" size={16} />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        autoFocus={autoFocus}
      />
    </div>
  )
}

// Several tick boxes where any number can be chosen (e.g. a user's roles)
export function CheckboxGroup({ label, options, value, onChange, error, hint }) {
  const toggle = (optionValue) =>
    onChange(value.includes(optionValue) ? value.filter((item) => item !== optionValue) : [...value, optionValue])

  return (
    <fieldset className="field checkbox-group">
      {label && (
        <legend className="field-label">
          {label}
          <span className="required">*</span>
        </legend>
      )}
      <div className="checkbox-options">
        {options.map((option) => (
          <label key={option.value} className={value.includes(option.value) ? 'checkbox-card checked' : 'checkbox-card'}>
            <input
              type="checkbox"
              checked={value.includes(option.value)}
              onChange={() => toggle(option.value)}
              aria-label={option.label}
            />
            <span>
              <span className="checkbox-title">{option.label}</span>
              {option.description && <span className="checkbox-description">{option.description}</span>}
            </span>
          </label>
        ))}
      </div>
      {error ? <span className="field-error">{error}</span> : hint && <span className="field-hint">{hint}</span>}
    </fieldset>
  )
}

// A filter icon button that opens a panel of filters.
// `activeCount` shows how many filters are in use; `onClear` resets them.
export function FilterButton({ activeCount = 0, onClear, children }) {
  const [open, setOpen] = useState(false)
  const box = useRef(null)

  // Close the panel when clicking anywhere outside it
  useEffect(() => {
    if (!open) return undefined
    const onClick = (event) => {
      if (box.current && !box.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <div className="filter-box" ref={box}>
      <button
        type="button"
        className={activeCount ? 'btn btn-secondary filter-button active' : 'btn btn-secondary filter-button'}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <Icon name="filter" size={16} /> Filters
        {activeCount > 0 && <span className="filter-count">{activeCount}</span>}
      </button>
      {open && (
        <div className="filter-panel" role="dialog" aria-label="Filters">
          {children}
          <div className="filter-panel-footer">
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClear} disabled={!activeCount}>
              Clear all
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => setOpen(false)}>
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// A row of buttons where exactly one is selected (e.g. Active / Deleted / All)
export function Segmented({ options, value, onChange }) {
  return (
    <div className="segmented" role="group">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={option.value === value ? 'active' : ''}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

// A pop-up window. Closes with the ✕ button, the Escape key or a click outside.
export function Modal({ title, subtitle, onClose, children, footer, wide = false }) {
  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className={wide ? 'modal wide' : 'modal'} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-header">
          <div>
            <h2>{title}</h2>
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close">
            <Icon name="x" />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}

// "Are you sure?" pop-up used before deleting or blocking something
export function ConfirmDialog({ title, children, confirmLabel = 'Confirm', danger = false, busy = false, error, onConfirm, onCancel }) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className={danger ? 'btn btn-danger' : 'btn btn-primary'}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </>
      }
    >
      <div className="confirm-text">{children}</div>
      <Alert>{error}</Alert>
    </Modal>
  )
}

export function Avatar({ name, size = 36 }) {
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.38 }}>
      {initials(name)}
    </span>
  )
}
