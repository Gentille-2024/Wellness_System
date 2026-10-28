import { useState } from 'react'
import api, { errorMessage } from '../api/client'
import { ConfirmDialog } from '../components/ui'

// What each action does, shown in the "Are you sure?" pop-up
const ACTIONS = {
  deactivate: {
    title: (c) => `Deactivate ${c.name}?`,
    button: 'Deactivate',
    danger: true,
    text: 'EUCL employees won’t see it and no new visits can be recorded. Its staff can still log in to see their records. You can activate it again at any time.',
    run: (c) => api.post(`/companies/${c.id}/deactivate/`),
    done: (c) => `${c.name} was deactivated.`,
  },
  activate: {
    title: (c) => `Activate ${c.name}?`,
    button: 'Activate',
    text: 'EUCL employees will see it again and its receptionists can record visits.',
    run: (c) => api.post(`/companies/${c.id}/activate/`),
    done: (c) => `${c.name} is open again.`,
  },
  delete: {
    title: (c) => `Delete ${c.name}?`,
    button: 'Delete company',
    danger: true,
    text: 'The company is archived and its staff can no longer log in. No visits or payments are erased, and you can restore it later.',
    run: (c) => api.delete(`/companies/${c.id}/`),
    done: (c) => `${c.name} was deleted. Its history is kept.`,
  },
  restore: {
    title: (c) => `Restore ${c.name}?`,
    button: 'Restore',
    text: 'The company comes back and its staff can log in again.',
    run: (c) => api.post(`/companies/${c.id}/restore/`),
    done: (c) => `${c.name} was restored.`,
  },
}

// Hook + dialog for the four company actions, shared with the company page
export default function useCompanyActions(onDone) {
  const [pending, setPending] = useState(null) // { company, action }
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const confirm = async () => {
    const { company, action } = pending
    setBusy(true)
    setError('')
    try {
      await ACTIONS[action].run(company)
      onDone(ACTIONS[action].done(company))
      setPending(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const dialog = pending && (
    <ConfirmDialog
      title={ACTIONS[pending.action].title(pending.company)}
      confirmLabel={ACTIONS[pending.action].button}
      danger={ACTIONS[pending.action].danger}
      busy={busy}
      error={error}
      onConfirm={confirm}
      onCancel={() => {
        setPending(null)
        setError('')
      }}
    >
      <p>{ACTIONS[pending.action].text}</p>
    </ConfirmDialog>
  )

  return { ask: (company, action) => setPending({ company, action }), dialog }
}
