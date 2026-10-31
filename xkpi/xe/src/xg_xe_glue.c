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
 * The fake-offset of a dumb buffer for mmap (Linux's drm_gem_ttm_dumb_map_offset, which drm-kmod does not build):
 * every GEM object has a VMA offset node, and that node's address is the mmap offset.
 */
int drm_gem_ttm_dumb_map_offset(struct drm_file *file, struct drm_device *dev, uint32_t handle, uint64_t *offset)
{
	struct drm_gem_object *gem = drm_gem_object_lookup(file, handle);

	if (gem == NULL)
		return -ENOENT;
	*offset = drm_vma_node_offset_addr(&gem->vma_node);
	drm_gem_object_put(gem);
	return 0;
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
