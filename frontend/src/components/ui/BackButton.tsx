import { useNavigate } from 'react-router-dom'
import './BackButton.css'

interface BackButtonProps {
  /** Where to go if there's no in-app history to go back to (e.g. the page
   *  was opened directly via URL). Falls back to browser history otherwise. */
  fallbackTo: string
  label?: string
}

/**
 * Small "← Back" control for pages reached by drilling into something
 * (e.g. a company's requisition → its pipeline) rather than by a top-level
 * Navbar link. Uses in-app history when there is any, so it behaves like a
 * real back button rather than always bouncing to a fixed route.
 */
export default function BackButton({ fallbackTo, label = 'Back' }: BackButtonProps) {
  const navigate = useNavigate()

  function handleClick() {
    if (window.history.state && window.history.state.idx > 0) {
      navigate(-1)
    } else {
      navigate(fallbackTo)
    }
  }

  return (
    <button type="button" className="back-button" onClick={handleClick}>
      <span aria-hidden="true">←</span> {label}
    </button>
  )
}