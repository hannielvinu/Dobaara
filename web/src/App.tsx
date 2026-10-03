import { Badge, Box, Text } from '@razorpay/blade/components'
import { useEffect, useState, type ReactNode } from 'react'
import Cases from './pages/Cases'
import Compliance from './pages/Compliance'
import Console from './pages/Console'
import Experiment from './pages/Experiment'
import HowItWorks from './pages/HowItWorks'
import Overview from './pages/Overview'
import Replies from './pages/Replies'
import { useCases, useResults } from './data'

type Route = { id: string; title: string; icon: ReactNode }

const I = (d: string) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
)

const ROUTES: Route[] = [
  { id: 'overview', title: 'Overview', icon: I('M3 12l9-8 9 8M5 10v10h14V10') },
  { id: 'cases', title: 'Case replays', icon: I('M4 6h16M4 12h16M4 18h10') },
  { id: 'experiment', title: 'Experiment', icon: I('M4 20V10M10 20V4M16 20v-7M22 20H2') },
  { id: 'replies', title: 'Reply understanding', icon: I('M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z') },
  { id: 'compliance', title: 'Compliance & audit', icon: I('M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z') },
  { id: 'console', title: 'Live console', icon: I('M4 17l6-6-6-6M12 19h8') },
  { id: 'how', title: 'How it works', icon: I('M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 16v-4M12 8h.01') },
]

function useRoute(): string {
  const read = () => (window.location.hash.replace(/^#\/?/, '').split('?')[0] || 'overview')
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const on = () => {
      setRoute(read())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="#305EFF" />
      <path d="M9 16a7 7 0 0 1 12-4.9M23 16a7 7 0 0 1-12 4.9" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <path d="M21.5 7.5v4h-4M10.5 24.5v-4h4" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function App() {
  const route = useRoute()
  const results = useResults()
  const cases = useCases()
  const current = ROUTES.find((r) => r.id === route) ?? ROUTES[0]

  let page: ReactNode
  switch (current.id) {
    case 'cases':
      page = <Cases cases={cases} />
      break
    case 'experiment':
      page = <Experiment results={results} />
      break
    case 'replies':
      page = <Replies results={results} />
      break
    case 'compliance':
      page = <Compliance results={results} cases={cases} />
      break
    case 'console':
      page = <Console />
      break
    case 'how':
      page = <HowItWorks />
      break
    default:
      page = <Overview results={results} />
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <aside
        className="sidebar"
        style={{ width: 248, flex: 'none', background: '#0b1530', padding: '20px 14px', display: 'flex', flexDirection: 'column', gap: 4, position: 'sticky', top: 0, height: '100vh' }}
      >
        <a href="#/overview" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 8px 18px', textDecoration: 'none' }}>
          <Logo />
          <span style={{ color: '#fff', fontFamily: "'TASA Orbiter', Inter, sans-serif", fontWeight: 700, fontSize: 20, letterSpacing: 0.2 }}>Dobaara</span>
        </a>
        <span style={{ color: '#7486ad', fontSize: 11, fontWeight: 600, letterSpacing: 0.8, padding: '6px 12px' }}>REVENUE RECOVERY</span>
        {ROUTES.map((r) => (
          <a key={r.id} href={`#/${r.id}`} className={`navlink${r.id === current.id ? ' active' : ''}`}>
            {r.icon}
            {r.title}
          </a>
        ))}
        <div style={{ marginTop: 'auto', padding: 12, borderRadius: 10, background: 'rgba(255,255,255,0.05)', color: '#9fb0d4', fontSize: 12, lineHeight: 1.5 }}>
          Razorpay AI Buildathon 2026
          <br />
          Track 03 · AI Revenue Recovery
        </div>
      </aside>

      <main style={{ flex: 1, minWidth: 0 }}>
        <nav className="mobile-nav">
          {ROUTES.map((r) => (
            <a key={r.id} href={`#/${r.id}`} className={r.id === current.id ? 'active' : ''}>
              {r.title}
            </a>
          ))}
        </nav>
        <Box
          display="flex"
          alignItems="center"
          justifyContent="space-between"
          paddingX="spacing.7"
          paddingY="spacing.5"
          backgroundColor="surface.background.gray.intense"
          borderBottomWidth="thin"
          borderBottomColor="surface.border.gray.muted"
          gap="spacing.4"
          flexWrap="wrap"
        >
          <Box display="flex" alignItems="center" gap="spacing.3">
            <Text size="large" weight="semibold">
              {current.title}
            </Text>
            <Badge color="notice" emphasis="subtle">
              Test mode
            </Badge>
          </Box>
          <Text size="small" color="surface.text.gray.muted">
            Failed UPI AutoPay & eNACH debits · recovered within the rules
          </Text>
        </Box>
        <Box paddingX="spacing.7" paddingY="spacing.7" maxWidth="1280px">
          {page}
        </Box>
      </main>
    </div>
  )
}
