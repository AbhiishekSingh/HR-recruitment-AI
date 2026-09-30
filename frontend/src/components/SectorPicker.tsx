import { useState } from 'react'
import { SECTOR_LIST } from '../types'
import './SectorPicker.css'

const CUSTOM_OPTION = '__custom__'

interface SectorPickerProps {
  value: string
  onChange: (value: string) => void
  label?: string
  helpText?: string
}

/** A sector <select> that also lets the recruiter type a brand-new sector
 *  name not in the built-in suggested list (SECTOR_LIST). Sectors are just
 *  a free-text column (Candidate.sector) — there's no fixed enum in the
 *  database — so any name typed here is a real, usable sector as soon as a
 *  candidate is tagged with it, and it appears as its own card on the
 *  Categories page (CandidateCategoriesPage.tsx includes any sector present
 *  in the counts response, not just the built-in ones).
 *
 *  Always controlled (value/onChange) — used by both the bulk-upload flow
 *  (plain component state, pins every uploaded resume in this batch to the
 *  chosen sector) and the manual "Add candidate" form (lifted into state
 *  instead of read via FormData, so this component doesn't need an
 *  uncontrolled mode too). */
export default function SectorPicker({ value, onChange, label = 'Sector', helpText }: SectorPickerProps) {
  // True once "+ Add a new sector…" is chosen, so the free-text input stays
  // showing even while it's empty (otherwise there'd be no way to tell the
  // "not set" and "mid-typing a custom name" states apart once the field is
  // cleared).
  const [customMode, setCustomMode] = useState(false)
  const knownSector = !customMode && (value === '' || SECTOR_LIST.includes(value as any))

  return (
    <div className="field">
      <label>{label} (optional{helpText ? ` — ${helpText}` : ' — leave blank to auto-detect from the resume'})</label>
      {knownSector ? (
        <select
          value={value}
          onChange={(e) => {
            if (e.target.value === CUSTOM_OPTION) {
              setCustomMode(true)
              onChange('')
            } else {
              onChange(e.target.value)
            }
          }}
        >
          <option value="">Not set</option>
          {SECTOR_LIST.map((s) => <option key={s} value={s}>{s}</option>)}
          <option value={CUSTOM_OPTION}>+ Add a new sector…</option>
        </select>
      ) : (
        <div className="sector-picker-custom-row">
          <input
            autoFocus
            placeholder="Type the new sector name"
            value={value}
            onChange={(e) => onChange(e.target.value)}
          />
          <button
            type="button"
            className="link-button"
            onClick={() => { setCustomMode(false); onChange('') }}
          >
            Use list instead
          </button>
        </div>
      )}
    </div>
  )
}
