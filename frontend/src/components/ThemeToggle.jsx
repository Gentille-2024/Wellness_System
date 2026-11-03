import { useState } from 'react'
import Icon from './Icon'

// The theme is set on <html data-theme="…"> by a small script in index.html
// before the page draws; these buttons switch it and remember the choice.
const THEMES = [
  { value: 'light', label: 'Light', icon: 'sun' },
  { value: 'dark', label: 'Dark', icon: 'moon' },
  { value: 'ocean', label: 'Ocean', icon: 'wave' },
]
const current = () => {
  const theme = document.documentElement.dataset.theme
  return THEMES.some((t) => t.value === theme) ? theme : 'light'
}

function applyTheme(next) {
  document.documentElement.dataset.theme = next
  try {
    localStorage.setItem('theme', next)
  } catch {
    // Private browsing: the choice just isn't remembered
  }
}

export default function ThemeToggle({ className = '' }) {
  const [theme, setTheme] = useState(current)

  const choose = (next) => {
    applyTheme(next)
    setTheme(next)
  }

  return (
    <div className={`theme-switch ${className}`.trim()} role="radiogroup" aria-label="Theme">
      {THEMES.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={theme === option.value}
          className={theme === option.value ? 'theme-option active' : 'theme-option'}
          onClick={() => choose(option.value)}
          title={`${option.label} theme`}
          aria-label={`${option.label} theme`}
        >
          <Icon name={option.icon} size={16} />
        </button>
      ))}
    </div>
  )
}
