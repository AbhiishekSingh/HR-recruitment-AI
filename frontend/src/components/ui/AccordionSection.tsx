import { ReactNode, useState } from 'react'
import './AccordionSection.css'

interface AccordionSectionProps {
  title: string
  children: ReactNode
  defaultOpen?: boolean
}

/**
 * Collapsible section used to group a long form into named blocks (Basic
 * Details, Profile Screening, ...). Each section opens/closes independently
 * so more than one can be expanded at once.
 */
export default function AccordionSection({ title, children, defaultOpen = false }: AccordionSectionProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={`accordion-section ${open ? 'accordion-section-open' : ''}`}>
      <button
        type="button"
        className="accordion-header"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>{title}</span>
        <span className="accordion-chevron" aria-hidden="true">{open ? '˄' : '˅'}</span>
      </button>
      {open && <div className="accordion-body">{children}</div>}
    </div>
  )
}