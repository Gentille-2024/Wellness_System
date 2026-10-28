// Transparent PNG; the light version (white text) suits the dark sidebar
import regLogo from '../assets/reg-logo-light.png'
import Icon from './Icon'

// REG logo on top, then the system's own logo and name
export default function Brand() {
  return (
    <div className="brand-block">
      <img src={regLogo} alt="Rwanda Energy Group (REG)" className="reg-logo" width="156" height="60" />
      <div className="sidebar-brand">
        <span className="brand-mark">
          <Icon name="leaf" size={20} />
        </span>
        <div>
          <div className="brand-name">Wellness</div>
          <div className="brand-sub">Management System</div>
        </div>
      </div>
    </div>
  )
}
