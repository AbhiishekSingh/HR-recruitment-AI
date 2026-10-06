import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updateJob } from '../api/jobs'
import type { JobPosting } from '../types'
import RequisitionForm, { RequisitionSubmit, valuesFromJob } from './RequisitionForm'

interface EditJobModalProps {
  job: JobPosting
  onClose: () => void
}

/** Edit every detail of a posted job, including its skill groups and
 *  synonyms. Free smart scores update instantly; any AI scores already done
 *  for this job are marked "out of date" so HR can choose to re-score. */
export default function EditJobModal({ job, onClose }: EditJobModalProps) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (data: RequisitionSubmit) =>
      updateJob(job.id, {
        title: data.title,
        locations: data.locations,
        budget_min: data.budget_min,
        budget_max: data.budget_max,
        experience_min: data.experience_min,
        experience_max: data.experience_max,
        max_notice_days: data.max_notice_days,
        required_skills: data.required_skills,
        skill_groups: data.skill_groups,
        related_titles: data.related_titles,
        raw_text: data.raw_text,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      queryClient.invalidateQueries({ queryKey: ['job', job.id] })
      queryClient.invalidateQueries({ queryKey: ['pipeline', job.id] })
      onClose()
    },
  })

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-panel-wide" onClick={(e) => e.stopPropagation()}>
        <h2>Edit job: {job.title}</h2>
        <p className="muted">
          Candidate rankings (free smart scores) update as soon as you save. Any AI scores already done for this job
          will show as "out of date"; you can re-score them from the pipeline.
          {!job.has_custom_groups && ' The skill groups below were created automatically from the required skills; adjust them as needed.'}
        </p>
        <RequisitionForm
          initialValues={valuesFromJob(job)}
          submitLabel={mutation.isPending ? 'Saving...' : 'Save changes'}
          loading={mutation.isPending}
          error={mutation.isError ? ((mutation.error as any)?.response?.data?.detail || 'Could not save the job.') : null}
          onSubmit={(data) => mutation.mutate(data)}
          onCancel={onClose}
        />
      </div>
    </div>
  )
}
