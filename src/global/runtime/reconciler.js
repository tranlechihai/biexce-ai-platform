import fs from "node:fs"

import {
  appendJobEvent,
  reconcileJobBoard,
} from "./job-board.js"
import {
  loadSchedulerState,
  recoverSchedulerBlockers,
  releaseSchedulerJob,
  schedulerStatePath,
} from "./scheduler.js"


const REQUEUEABLE_JOB_STATUSES = new Set([
  "QUEUED",
  "RETRYING",
  "CANCELLED",
  "TIMED_OUT",
])


export function reconcileRuntimeState(
  projectRoot,
  {
    recoverBlockers = false,
    allowStandard = false,
    phaseByTask = {},
  } = {},
) {
  const boardResult = reconcileJobBoard(projectRoot)
  const result = {
    recovered_jobs: [...boardResult.recovered],
    released_scheduler_jobs: [],
    inconsistencies: [],
    recovered_tasks: [],
    recovered_routes: {},
    recovery_reasons: {},
  }
  if (!fs.existsSync(schedulerStatePath(projectRoot))) return result

  const scheduler = loadSchedulerState(projectRoot)
  for (const task of Object.values(scheduler.tasks)) {
    if (task.status !== "RUNNING" || !task.active_job_id) continue
    const job = boardResult.board.jobs[task.active_job_id] || null
    if (job === null) {
      result.inconsistencies.push({
        task_id: task.task_id,
        job_id: task.active_job_id,
        reason: "SCHEDULER_JOB_MISSING",
      })
      continue
    }
    if (!REQUEUEABLE_JOB_STATUSES.has(job.status)) continue

    const released = releaseSchedulerJob(
      projectRoot,
      task.active_job_id,
      `Runtime reconciler requeued ${job.status} job after restart`,
      { recoverable: true },
    )
    if (!released.changed) continue
    result.released_scheduler_jobs.push(task.active_job_id)
    appendJobEvent(projectRoot, {
      event: "RUNTIME_STATE_RECONCILED",
      job_id: task.active_job_id,
      task_id: task.task_id,
      board_status: job.status,
      scheduler_status_before: task.status,
      scheduler_status_after: released.task.status,
    })
  }
  if (recoverBlockers) {
    const recovery = recoverSchedulerBlockers(projectRoot, {
      allowStandard,
      phaseByTask,
    })
    result.recovered_tasks = recovery.recovered_tasks
    result.recovered_routes = recovery.recovered_routes
    result.recovery_reasons = recovery.recovery_reasons
    for (const taskID of recovery.recovered_tasks) {
      appendJobEvent(projectRoot, {
        event: "RUNTIME_TASK_RECOVERED",
        task_id: taskID,
        recovery_route: recovery.recovered_routes[taskID] || null,
        recovery_reason: recovery.recovery_reasons[taskID] || null,
      })
    }
  }
  return result
}
