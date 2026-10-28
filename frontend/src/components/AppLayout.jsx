import { useState } from 'react'
import { NavLink, Outlet } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { navFor } from '../navigation'
import Brand from './Brand'
import Icon from './Icon'
import { Avatar } from './ui'

// The frame around every page after login: sidebar menu + top bar + page
export default function AppLayout() {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false) // sidebar on small screens
  const sections = navFor(user) // only the links this user's permissions allow
  const displayName = user.full_name || user.username
  const today = new Date().toLocaleDateString([], {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })

  return (
    <div className="app">
      <aside className={menuOpen ? 'sidebar open' : 'sidebar'}>
        <Brand />

        <nav className="sidebar-nav" aria-label="Main menu">
          {sections.map((section) => (
            <div key={section.section} className="nav-section">
              <div className="nav-section-title">{section.section}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
                  onClick={() => setMenuOpen(false)}
                >
                  <Icon name={item.icon} />
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-user">
          <Avatar name={displayName} />
          <div className="sidebar-user-text">
            <div className="sidebar-user-name">{displayName}</div>
            <div className="sidebar-user-role">{user.role_names.join(', ') || 'No role'}</div>
          </div>
          <button type="button" className="btn-icon sidebar-logout" onClick={logout} aria-label="Log out" title="Log out">
            <Icon name="logout" />
          </button>
        </div>
      </aside>

      {menuOpen && <div className="sidebar-backdrop" onClick={() => setMenuOpen(false)} />}

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="btn-icon menu-button"
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
          >
            <Icon name="menu" />
          </button>
          <div className="topbar-context">
            {user.company?.name ?? 'EUCL Wellness Management System'}
          </div>
          <div className="topbar-date">{today}</div>
        </header>

        <main className="page">
          {/* The current page is rendered here */}
          <Outlet />
        </main>
      </div>
    </div>
  )
}
