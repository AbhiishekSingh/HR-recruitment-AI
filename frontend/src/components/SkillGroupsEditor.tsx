import { useEffect, useState } from 'react'
import type { SkillGroup } from '../types'
import './SkillGroupsEditor.css'

const TYPE_LABELS: Record<SkillGroup['type'], string> = {
  must: 'Must-have',
  nice: 'Nice-to-have',
  soft: 'Not scored (soft skill)',
}

const toList = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean)

interface SkillGroupsEditorProps {
  groups: SkillGroup[]
  onChange: (groups: SkillGroup[]) => void
  /** highlight when no must-have skills are set */
  showMissing?: boolean
}

/**
 * Edits a job's scoring groups. Each group counts ONCE in the score: a
 * candidate needs any one of its skills (or synonyms). Keeps text inputs as
 * the person typed them; lists are split on commas.
 */
export default function SkillGroupsEditor({ groups, onChange, showMissing }: SkillGroupsEditorProps) {
  function update(i: number, patch: Partial<SkillGroup>) {
    onChange(groups.map((g, idx) => (idx === i ? { ...g, ...patch } : g)))
  }
  function remove(i: number) {
    onChange(groups.filter((_, idx) => idx !== i))
  }
  function add(type: SkillGroup['type']) {
    onChange([...groups, { name: '', type, skills: [], synonyms: [] }])
  }

  const mustCount = groups.filter((g) => g.type === 'must' && g.skills.length > 0).length

  return (
    <div className={`skill-groups${showMissing && mustCount === 0 ? ' skill-groups-missing' : ''}`}>
      <p className="muted skill-groups-help">
        Each group counts <strong>once</strong> in the score: a candidate needs <strong>any one</strong> of its skills
        or synonyms. Put alternatives in one group (e.g. "BI tool: Tableau, Power BI"). Soft skills are checked in the
        screening call, not scored.
      </p>
      {showMissing && mustCount === 0 && <p className="field-missing-hint">Add at least one must-have group</p>}

      {groups.map((g, i) => (
        <div key={i} className={`skill-group skill-group-${g.type}`}>
          <div className="skill-group-head">
            <input
              className="skill-group-name"
              placeholder="Group name (e.g. SQL & query work)"
              value={g.name}
              onChange={(e) => update(i, { name: e.target.value })}
            />
            <select value={g.type} onChange={(e) => update(i, { type: e.target.value as SkillGroup['type'] })}>
              {(Object.keys(TYPE_LABELS) as SkillGroup['type'][]).map((t) => (
                <option key={t} value={t}>{TYPE_LABELS[t]}</option>
              ))}
            </select>
            <button type="button" className="link-button muted" onClick={() => remove(i)} aria-label="Remove group">Remove</button>
          </div>
          <label className="skill-group-label">Skills (comma separated)</label>
          <GroupListInput value={g.skills} onChange={(skills) => update(i, { skills })} placeholder="SQL, Stored Procedures, CTEs" />
          {g.type !== 'soft' && (
            <>
              <label className="skill-group-label">Synonyms for this job (comma separated, optional)</label>
              <GroupListInput value={g.synonyms} onChange={(synonyms) => update(i, { synonyms })} placeholder="T-SQL, MS SQL Server" />
            </>
          )}
        </div>
      ))}

      <div className="row skill-groups-add">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => add('must')}>+ Must-have group</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => add('nice')}>+ Nice-to-have group</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => add('soft')}>+ Soft skills</button>
      </div>
    </div>
  )
}

/** Comma-separated list input. Keeps the raw text while typing (so a
 *  trailing ", " isn't swallowed), reports the parsed list, and re-syncs when
 *  the list is changed from outside (group removed, filled from a JD). */
function GroupListInput({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder: string }) {
  const [text, setText] = useState(value.join(', '))
  const joined = value.join('|')
  useEffect(() => {
    if (toList(text).join('|') !== joined) setText(value.join(', '))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined])
  return (
    <input
      className="skill-group-input"
      placeholder={placeholder}
      value={text}
      onChange={(e) => {
        setText(e.target.value)
        const list = toList(e.target.value)
        if (list.join('|') !== joined) onChange(list)
      }}
    />
  )
}
