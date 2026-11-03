import api from './client'
import { ME_TOOL_URL } from '../navigation'

// The M&E tool is a separate website. To open it signed in as THIS user (and
// never as whoever used the M&E tool in this browser before), we ask the
// wellness API for a one-time ticket (valid one minute) and send it along.
export async function meToolSignInUrl() {
  const { data } = await api.post('/me-tool/ticket/')
  return `${ME_TOOL_URL}/accounts/sso/?ticket=${encodeURIComponent(data.ticket)}`
}

// "M&E tool" in the menu: opens a new tab right away (so the browser doesn't
// block it), then sends it to the sign-in link once we have the ticket.
export async function openMeTool() {
  const tab = window.open('about:blank', '_blank')
  try {
    const url = await meToolSignInUrl()
    if (tab) {
      tab.opener = null
      tab.location.href = url
    } else {
      window.location.assign(url)
    }
  } catch {
    // No ticket (e.g. the wellness API is down): the M&E tool's own sign-in page
    if (tab) tab.location.href = ME_TOOL_URL
  }
}
