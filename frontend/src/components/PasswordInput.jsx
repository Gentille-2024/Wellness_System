import { useState } from 'react'
import Icon from './Icon'

// A password box with an eye button to show or hide what was typed
export default function PasswordInput(props) {
  const [shown, setShown] = useState(false)
  return (
    <span className="password-field">
      <input {...props} type={shown ? 'text' : 'password'} />
      <button
        type="button"
        className="password-toggle"
        onClick={() => setShown((value) => !value)}
        aria-label={shown ? 'Hide password' : 'Show password'}
        title={shown ? 'Hide password' : 'Show password'}
        aria-pressed={shown}
      >
        <Icon name={shown ? 'eyeOff' : 'eye'} size={18} />
      </button>
    </span>
  )
}
