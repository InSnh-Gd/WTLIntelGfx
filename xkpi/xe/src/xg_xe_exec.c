// SPDX-License-Identifier: MIT
/* M1 diagnostics use the same kernel queue path as xe_gt_record_default_lrcs. */
#include <linux/pci.h>
#include <linux/dma-fence.h>
#include <drm/drm_managed.h>
#include "xe_bb.h"
#include "xe_sa.h"
#include "xe_device.h"
#include "xe_exec_queue.h"
#include "xe_force_wake.h"
#include "xe_gt.h"
#include "xe_hw_engine.h"
#include "xe_mmio.h"
#include "xe_pm.h"
#include "xe_sched_job.h"
#include "xe_step.h"
#include "regs/xe_gt_regs.h"
#include "xg_xe.h"

/* The shim increments this on each IOKit interrupt filter invocation. */
extern unsigned int xg_pci_irqs;

static struct xe_device *xg_xe_find(struct pci_dev **pdevp)
{
 struct pci_dev *pdev = NULL;
 while ((pdev = lkpi_pci_get_device(PCI_VENDOR_ID_INTEL, PCI_ANY_ID, pdev)) != NULL) {
  struct xe_device *xe = pdev_to_xe_device(pdev);
  if (xe) {
   *pdevp = pdev;
   return xe;
  }
 }
 return NULL;
}

int xg_xe_state(struct xg_xe_state *st)
{
 struct pci_dev *pdev;
 struct xe_device *xe;
 struct xe_gt *gt;
 struct xe_hw_engine *hwe;
 enum xe_hw_engine_id h;
 u8 id;
 memset(st, 0, sizeof(*st));
 st->render_minor = -1;
 xe = xg_xe_find(&pdev);
 if (!xe) return -ENODEV;
 xe_pm_runtime_get(xe);
 st->healthy = 1;
 st->graphics_verx100 = GRAPHICS_VERx100(xe);
 st->media_verx100 = MEDIA_VERx100(xe);
 st->platform = xe->info.platform;
 strscpy(st->platform_name, xe->info.platform_name, sizeof(st->platform_name));
 st->devid = pdev->device;
 st->revid = pdev->revision;
 st->irq_enabled = atomic_read(&xe->irq.enabled);
 st->vectors = pdev->msix_enabled ? xe->irq.msix.nvec : (pdev->msi_enabled ? 1 : 0);
 if (xe->drm.render) st->render_minor = xe->drm.render->index;
 for_each_gt(gt, xe, id) {
  struct xg_xe_gt_state *g;
  struct xe_uc_fw *fw = &gt->uc.guc.fw;
  struct xe_uc_fw_version *v = &fw->versions.found[XE_UC_FW_VER_RELEASE];
  unsigned int ref;
  if (st->gts == XG_XE_MAX_GTS) { st->healthy = 0; break; }
  g = &st->gt[st->gts++];
  g->id = id;
  g->media = xe_gt_is_media_type(gt);
  ref = xe_force_wake_get(gt_to_fw(gt), XE_FW_GT);
  g->forcewake = xe_force_wake_ref_has_domain(ref, XE_FW_GT);
  if (g->forcewake)
   g->gmd = xe_mmio_read32(&gt->mmio, GMD_ID);
  xe_force_wake_put(gt_to_fw(gt), ref);
  if (g->media) st->media_gmd = g->gmd;
  else st->graphics_gmd = g->gmd;
  g->arch = REG_FIELD_GET(GMD_ID_ARCH_MASK, g->gmd);
  g->release = REG_FIELD_GET(GMD_ID_RELEASE_MASK, g->gmd);
  g->revid = REG_FIELD_GET(GMD_ID_REVID, g->gmd);
  g->guc_status = fw->status;
  g->guc_major = v->major; g->guc_minor = v->minor; g->guc_patch = v->patch;
  g->running = fw->status == XE_UC_FIRMWARE_RUNNING;
  g->submission = READ_ONCE(gt->uc.guc.submission_state.enabled) &&
                  !atomic_read(&gt->uc.guc.submission_state.stopped);
  strscpy(g->step, xe_step_name(g->media ? xe->info.step.media : xe->info.step.graphics), sizeof(g->step));
  st->healthy &= g->running && g->submission && g->forcewake;
  for_each_hw_engine(hwe, gt, h) st->engines++;
  printf("xegfx: GT%u %s GMD_ID=%#x arch=%u release=%u revid=%u step=%s GuC status=%d version=%u.%u.%u running=%d submission=%d forcewake=%d\n",
      g->id, g->media ? "media" : "graphics", g->gmd, g->arch, g->release, g->revid, g->step,
      g->guc_status, g->guc_major, g->guc_minor, g->guc_patch, g->running, g->submission, g->forcewake);
 }
 st->healthy &= st->gts > 0 && st->irq_enabled && st->vectors > 0;
 printf("xegfx: xe platform=%s(%u) devid=%04x revid=%02x graphics=%u media=%u GMD[0d8c]=%#x GMD[380d8c]=%#x MSI vectors=%d irq-enabled=%d\n",
     st->platform_name, st->platform, st->devid, st->revid, st->graphics_verx100, st->media_verx100,
     st->graphics_gmd, st->media_gmd, st->vectors, st->irq_enabled);
 xe_pm_runtime_put(xe);
 pci_dev_put(pdev);
 return 0;
}

struct xg_xe_exec_pool {
 struct xe_sa_manager *manager;
 struct dma_fence *pending;
};

static void xg_xe_exec_pool_fini(struct drm_device *drm, void *arg)
{
 struct xg_xe_exec_pool *state = arg;
 dma_fence_put(state->pending);
}

/* gStageLock serializes diagnostics. Refuse retries until the last unfinished
 * batch completes; otherwise SA allocation could wait forever behind it. */
static struct xg_xe_exec_pool *xg_xe_exec_pool_get(struct xe_gt *gt)
{
 struct xg_xe_exec_pool *state = gt->m1_exec;
 struct xe_device *xe = gt_to_xe(gt);
 int err;
 if (!state) {
  state = drmm_kzalloc(&xe->drm, sizeof(*state), GFP_KERNEL);
  if (!state) return ERR_PTR(-ENOMEM);
  err = drmm_add_action_or_reset(&xe->drm, xg_xe_exec_pool_fini, state);
  if (err) return ERR_PTR(err);
  /* Cache failures too: retrying must not accumulate managed BOs. */
  state->manager = xe_sa_bo_manager_init(gt_to_tile(gt), SZ_128K, 64);
  gt->m1_exec = state;
 }
 if (IS_ERR(state->manager)) return ERR_CAST(state->manager);
 if (state->pending) {
  if (!dma_fence_is_signaled(state->pending)) return ERR_PTR(-EBUSY);
  dma_fence_put(state->pending);
  state->pending = NULL;
 }
 return state;
}

static struct xe_bb *xg_xe_bb_new(struct xe_sa_manager *pool)
{
 struct xe_bb *bb = kzalloc(sizeof(*bb), GFP_KERNEL);
 if (!bb) return ERR_PTR(-ENOMEM);
 bb->bo = xe_sa_bo_new(pool, SZ_2K);
 if (IS_ERR(bb->bo)) {
  int err = PTR_ERR(bb->bo);
  kfree(bb);
  return ERR_PTR(err);
 }
 bb->cs = xe_sa_bo_cpu_addr(bb->bo);
 return bb;
}

int xg_xe_exec(struct xg_xe_exec *ex, int timeout_ms)
{
 struct pci_dev *pdev;
 struct xe_device *xe;
 struct xe_gt *gt;
 struct xe_hw_engine *hwe;
 enum xe_hw_engine_id h;
 unsigned int irq0;
 unsigned long deadline;
 u8 id;
 memset(ex, 0, sizeof(*ex));
 if (timeout_ms <= 0 || timeout_ms > 2000) return -EINVAL;
 xe = xg_xe_find(&pdev);
 if (!xe) return -ENODEV;
 xe_pm_runtime_get(xe);
 irq0 = READ_ONCE(xg_pci_irqs);
 deadline = jiffies + msecs_to_jiffies(20000);
 for_each_gt(gt, xe, id) {
  for_each_hw_engine(hwe, gt, h) {
   struct xg_xe_exec_pool *state;
   struct xe_exec_queue *q;
   struct xe_bb *bb;
   struct xe_sched_job *job;
   struct dma_fence *fence;
   ktime_t t0 = ktime_get();
   long t;
   unsigned long remaining;
   int n = ex->engines;
   if (n == XG_XE_MAX_ENGINES) { ex->truncated = 1; goto out; }
   ex->engines++;
   snprintf(ex->name[n], sizeof(ex->name[n]), "gt%u-%s", id, hwe->name);
   if (gt->uc.guc.fw.status != XE_UC_FIRMWARE_RUNNING ||
       !gt->uc.guc.submission_state.enabled ||
       atomic_read(&gt->uc.guc.submission_state.stopped)) {
    ex->err[n] = -EIO; goto report;
   }
   if (time_after_eq(jiffies, deadline)) {
    ex->err[n] = -ETIMEDOUT; ex->truncated = 1; goto report;
   }
   state = xg_xe_exec_pool_get(gt);
   if (IS_ERR(state)) { ex->err[n] = PTR_ERR(state); goto report; }
   q = xe_exec_queue_create(xe, NULL, BIT(hwe->logical_instance), 1, hwe, EXEC_QUEUE_FLAG_KERNEL, 0);
   if (IS_ERR(q)) { ex->err[n] = PTR_ERR(q); goto report; }
   bb = xg_xe_bb_new(state->manager);
   if (IS_ERR(bb)) { ex->err[n] = PTR_ERR(bb); goto put_q; }
   /* xe_bb_create_job appends MI_BATCH_BUFFER_END to this empty batch. */
   job = xe_bb_create_job(q, bb);
   if (IS_ERR(job)) { ex->err[n] = PTR_ERR(job); xe_bb_free(bb, NULL); goto put_q; }
   xe_sched_job_arm(job);
   ex->seqno[n] = xe_sched_job_seqno(job);
   fence = dma_fence_get(&job->drm.s_fence->finished);
   xe_sched_job_push(job);
   ex->submitted[n] = 1;
   remaining = time_before(jiffies, deadline) ? deadline - jiffies : 0;
   t = dma_fence_wait_timeout(fence, false, min_t(unsigned long, remaining, msecs_to_jiffies(timeout_ms)));
   if (t <= 0) ex->err[n] = t < 0 ? (int)t : -ETIMEDOUT;
   else if (dma_fence_get_status(fence) < 0) ex->err[n] = dma_fence_get_status(fence);
   else { ex->completed[n] = ex->seqno[n]; ex->done++; }
   /* Defer suballocation reuse until FINISHED, including timeout/error paths. */
   if (!dma_fence_is_signaled(fence))
    state->pending = dma_fence_get(fence);
   xe_bb_free(bb, fence);
   dma_fence_put(fence);
   /* The common kill helper removes q from its VM; kernel queues have none. */
   if (ex->err[n]) q->ops->kill(q);
put_q:
   xe_exec_queue_put(q);
report:
   ex->ns[n] = ktime_to_ns(ktime_sub(ktime_get(), t0));
   printf("xegfx: %s submitted=%u seqno=%u completed=%u ns=%lld err=%d\n",
       ex->name[n], ex->submitted[n], ex->seqno[n], ex->completed[n], ex->ns[n], ex->err[n]);
   /* Stop on timeout: do not spend N timeouts behind a hung GT. */
   if (ex->err[n] == -ETIMEDOUT) goto out;
  }
 }
out:
 ex->irq_delta = READ_ONCE(xg_pci_irqs) - irq0;
 printf("xegfx: xe exec %d/%d completed, IRQ delta=%u (MSI %s)\n", ex->done, ex->engines, ex->irq_delta,
     ex->irq_delta ? "observed" : "NOT observed");
 xe_pm_runtime_put(xe);
 pci_dev_put(pdev);
 return 0;
}
