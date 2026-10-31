/* from NullMoth nvidia-macos-driver d96eaca gpu-port/xkpi/override/xe/nmx_xe_glue.c */
// SPDX-License-Identifier: MIT
/* Out-of-line pieces xe needs that neither drm-kmod nor LinuxKPI provides on macOS. */
#include <linux/mutex.h>
#include <drm/drm_managed.h>
#include <drm/drm_device.h>
#include <drm/drm_file.h>
#include <drm/drm_gem.h>
#include <drm/drm_vma_manager.h>

#include "intel_acpi.h"

void xg_xe_drmm_mutex_release(struct drm_device *dev, void *lock)
{
	mutex_destroy(lock);
}

/*
 * Intel's graphics _DSM: on Linux it is registered for vga_switcheroo (switchable-graphics laptops). macOS has no
 * switcheroo, and which GPU drives which output is fixed by the boot configuration, so nothing registers.
 */
void intel_register_dsm_handler(void)
{
}

void intel_unregister_dsm_handler(void)
{
}

/* A worker cannot adopt a process address space through the public XNU KPI.
 * Report all bytes uncopied; user-fence delivery and snapshots fail explicitly.
 * A later implementation must use the owning task's memory map. */
unsigned long xg_xe_mm_copy_to_user(struct mm_struct *mm, void *to,
    const void *from, unsigned long n)
{
 return n;
}

unsigned long xg_xe_mm_copy_from_user(struct mm_struct *mm, void *to,
    const void *from, unsigned long n)
{
 return n;
}

#include <linux/ioport.h>
#include <linux/mmu_notifier.h>
#include "xe_hmm.h"

/* Initialized from the shim's stage-3 DSM discovery before PCI registration. */
struct resource intel_graphics_stolen_res;

/* No ACPI video provider on XNU; never claim one was registered. */
void intel_acpi_video_register(struct intel_display *display) { }

/* CONFIG_HMM_MIRROR is off: never publish or DMA-map userspace pages.
 * No population can succeed, so free/unmap have no resources to release. */
int xe_hmm_userptr_populate_range(struct xe_userptr_vma *uvma, bool locked)
{
 return -EOPNOTSUPP;
}
void xe_hmm_userptr_free_sg(struct xe_userptr_vma *uvma) { }
void xe_hmm_userptr_unmap(struct xe_userptr_vma *uvma) { }

/* Match the shim notifier model: wired mappings never invalidate. Userptr
 * itself is rejected above; these do not enable unsupported HMM use. */
bool mmu_interval_check_retry(struct mmu_interval_notifier *mni, unsigned long seq)
{
 return mmu_interval_read_retry(mni, seq);
}
bool mmu_notifier_range_blockable(const struct mmu_notifier_range *range)
{
 return true;
}
