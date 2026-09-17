import { Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/Navbar'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import CompaniesPage from './pages/CompaniesPage'
import PipelinePage from './pages/PipelinePage'
import CandidatesDirectoryPage from './pages/CandidatesDirectoryPage'
import AnalyticsPage from './pages/AnalyticsPage'

export default function App() {
  return (
    <div className="app-shell">
      <Navbar />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/" element={<ProtectedRoute><Navigate to="/companies" replace /></ProtectedRoute>} />
        <Route path="/companies" element={<ProtectedRoute><CompaniesPage /></ProtectedRoute>} />
        <Route path="/pipeline/:jobId" element={<ProtectedRoute><PipelinePage /></ProtectedRoute>} />
        <Route path="/candidates" element={<ProtectedRoute><CandidatesDirectoryPage /></ProtectedRoute>} />
        <Route path="/analytics" element={<ProtectedRoute><AnalyticsPage /></ProtectedRoute>} />
      </Routes>
    </div>
  )
}
