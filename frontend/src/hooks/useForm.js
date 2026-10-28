import { useState } from 'react'
import { parseErrors } from '../api/client'

/**
 * Everything a form needs: values, per-field errors and a submitting flag.
 *
 *   const form = useForm({ name: '', email: '' })
 *   <form onSubmit={form.submit(async (values) => { await api.post(...) })}>
 *     <Field name="name" value={form.values.name} onChange={form.handleChange} error={form.errors.name} />
 */
export default function useForm(initialValues) {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)

  const handleChange = (event) => {
    const { name, value, type, checked } = event.target
    setValues((prev) => ({ ...prev, [name]: type === 'checkbox' ? checked : value }))
    // Typing in a field clears its old error
    setErrors((prev) => ({ ...prev, [name]: undefined }))
  }

  const submit = (request) => async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      await request(values)
    } catch (err) {
      const parsed = parseErrors(err)
      // Errors for fields this form doesn't show go into the general message
      const general = parsed._general ? [parsed._general] : []
      for (const [field, message] of Object.entries(parsed)) {
        if (field !== '_general' && !(field in initialValues)) general.push(`${field}: ${message}`)
      }
      setErrors({ ...parsed, _general: general.join('\n') || undefined })
    } finally {
      setSubmitting(false)
    }
  }

  return { values, setValues, errors, submitting, handleChange, submit }
}
