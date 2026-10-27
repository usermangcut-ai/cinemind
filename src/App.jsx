import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Overlays } from './components/layout'
import Landing from './pages/Landing'
import Chat from './pages/Chat'
import MyList from './pages/MyList'
import Login from './pages/Login'

export default function App() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  return (
    <>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/list" element={<MyList />} />
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Overlays />
    </>
  )
}
