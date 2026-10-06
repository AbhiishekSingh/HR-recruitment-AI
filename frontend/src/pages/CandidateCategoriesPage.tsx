import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getSectorCounts, getCandidateOverview } from '../api/candidates'
import PageHeader from '../components/ui/PageHeader'
import EmptyState from '../components/ui/EmptyState'
import Button from '../components/ui/Button'
import ResumeSearchPanel from '../components/ResumeSearchPanel'
import './CandidateCategoriesPage.css'

// Kept in the same order as the backend's fixed sector list (also mirrored
// in types/index.ts's SECTOR_LIST, validation.py's VALID_SECTORS, and
// prompts/resume_extraction.py's SECTOR_LIST -- update all four together)
// so cards show up in a stable, predictable order (rather than sorted by
// count, which would reshuffle every time counts change) -- a sector not
// yet in the counts response (no classified candidates yet) is simply
// skipped.
const SECTOR_ORDER = [
  'IT', 'HR', 'Sales', 'Marketing', 'Finance', 'Operations',
  'Customer Support', 'Legal', 'Design', 'Healthcare', 'Education',
  'Engineering', 'Manufacturing', 'Banking & Insurance',
  'Retail & E-commerce', 'Hospitality & Travel',
  'Construction & Real Estate', 'Logistics & Supply Chain',
  'Media & Entertainment', 'Government & Public Sector', 'Agriculture',
  'Other',
]

export default function CandidateCategoriesPage() {
  const navigate = useNavigate()
  // "categories" is the existing sector-cards landing view; "search" is the
  // full-text-across-every-resume search (ResumeSearchPanel), moved here
  // from the flat Candidates directory per feedback -- this page (not the
  // per-sector directory list) is where a recruiter lands first and where
  // this belongs.
  const [view, setView] = useState<'categories' | 'search'>('categories')
  const { data: counts, isLoading } = useQuery({
    queryKey: ['candidateSectorCounts'],
    queryFn: getSectorCounts,
  })
  // Total + the resumes that are NOT on a sector card (failed, still
  // processing, unclassified), so the numbers on this page always add up
  // to the real number of resumes uploaded.
  const { data: overview } = useQuery({
    queryKey: ['candidateOverview'],
    queryFn: getCandidateOverview,
    refetchInterval: 10000,
  })

  const countBySector = new Map((counts || []).map((c) => [c.sector, c.count]))
  // Known sectors first, in SECTOR_ORDER's stable order, exactly as before.
  // Appended after them: any sector present in the counts response that
  // ISN'T in SECTOR_ORDER -- a custom sector name a recruiter typed via
  // SectorPicker (on the upload form or the directory's inline "Edit")
  // rather than picking a suggested one. Without this, a custom sector
  // would have real candidates in it but never get a card to reach them
  // from. Sorted alphabetically among themselves so a growing set of custom
  // sectors doesn't reshuffle on every count change; kept before "Other" so
  // "Other" still reads as the catch-all it's meant to be.
  const known = SECTOR_ORDER.filter((s) => s !== 'Other' && countBySector.has(s))
  const custom = [...countBySector.keys()].filter((s) => !SECTOR_ORDER.includes(s)).sort()
  const sectorsToShow = [...known, ...custom, ...(countBySector.has('Other') ? ['Other'] : [])]

  return (
    <div className="container categories-page">
      <PageHeader
        title="Candidates"
        actions={
          // Routes to the directory page with a query flag telling it to
          // open the "Add one candidate" form immediately on load -- this
          // page intentionally shows only the sector cards, so adding a
          // candidate happens on the directory page, not here.
          <Button onClick={() => navigate('/candidates?openForm=1')}>+ Add one candidate</Button>
        }
      />

      <div className="add-mode-tabs">
        <button
          type="button"
          className={`add-mode-tab ${view === 'categories' ? 'add-mode-tab-active' : ''}`}
          onClick={() => setView('categories')}
        >
          Categories
        </button>
        <button
          type="button"
          className={`add-mode-tab ${view === 'search' ? 'add-mode-tab-active' : ''}`}
          onClick={() => setView('search')}
        >
          Search resumes
        </button>
      </div>

      {view === 'search' && <ResumeSearchPanel />}

      {view === 'categories' && (
        <>
          {overview && overview.total > 0 && (
            <>
              <p className="muted categories-total">
                <strong>{overview.total}</strong> resume{overview.total === 1 ? '' : 's'} in total
                {' '}= {overview.classified} in sector cards
                {overview.needs_attention > 0 && <> + {overview.needs_attention} need attention</>}
                {overview.processing > 0 && <> + {overview.processing} processing</>}
                {overview.unclassified > 0 && <> + {overview.unclassified} unclassified</>}
                {' · '}<button type="button" className="link-button" onClick={() => navigate('/candidates')}>View all</button>
              </p>
              <div className="sector-card-grid status-card-grid">
                {overview.needs_attention > 0 && (
                  <button className="card sector-card status-card status-card-bad" onClick={() => navigate('/candidates?status=attention')}>
                    <div className="sector-card-name">⚠ Needs attention</div>
                    <div className="sector-card-count">{overview.needs_attention} resume{overview.needs_attention === 1 ? '' : 's'}: AI processing failed, see reason &amp; retry</div>
                  </button>
                )}
                {overview.processing > 0 && (
                  <button className="card sector-card status-card status-card-warn" onClick={() => navigate('/candidates?status=processing')}>
                    <div className="sector-card-name">⏳ Still processing</div>
                    <div className="sector-card-count">{overview.processing} resume{overview.processing === 1 ? '' : 's'}</div>
                  </button>
                )}
                {overview.duplicates > 0 && (
                  <button className="card sector-card status-card status-card-warn" onClick={() => navigate('/candidates?status=duplicates')}>
                    <div className="sector-card-name">⧉ Possible duplicates</div>
                    <div className="sector-card-count">{overview.duplicates} resume{overview.duplicates === 1 ? '' : 's'} match an earlier candidate</div>
                  </button>
                )}
                {overview.unclassified > 0 && (
                  <button className="card sector-card status-card" onClick={() => navigate('/candidates?status=unclassified')}>
                    <div className="sector-card-name">Unclassified</div>
                    <div className="sector-card-count">{overview.unclassified} resume{overview.unclassified === 1 ? '' : 's'} with no sector</div>
                  </button>
                )}
              </div>
            </>
          )}

          {isLoading && <p className="muted">Loading...</p>}
          {!isLoading && sectorsToShow.length === 0 && (
            <EmptyState message="No candidates have been classified into a sector yet — upload some resumes to get started." />
          )}

          {sectorsToShow.length > 0 && (
            <div className="sector-card-grid">
              {sectorsToShow.map((sector) => (
                <button
                  key={sector}
                  className="card sector-card"
                  onClick={() => navigate(`/candidates?sector=${encodeURIComponent(sector)}`)}
                >
                  <div className="sector-card-name">{sector}</div>
                  <div className="sector-card-count">{countBySector.get(sector)} resume{countBySector.get(sector) === 1 ? '' : 's'}</div>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
