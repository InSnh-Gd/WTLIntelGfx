// SPDX-License-Identifier: MIT
/* from NullMoth nvidia-macos-driver d96eaca gpu-port/xkpi/override/xe/nmx_xe_module.c */
#include <linux/module.h>
#include <linux/moduleparam.h>

#include <drm/drm_drv.h>

#include "xe_hw_fence.h"
#include "xe_module.h"
#include "xe_observation.h"
#include "xe_pci.h"
#include "xe_pm.h"
#include "xe_sched_job.h"

SYSCTL_NODE(_hw, OID_AUTO, xe, CTLFLAG_RW | CTLFLAG_MPSAFE, 0, "xe driver parameters");

struct xe_modparam xe_modparam = {
	.force_execlist = false,
	.probe_display = true,		/* upstream default; runtime display switch comes later */
	.force_vram_bar_size = 0,	/* the BAR as the firmware sized it */
	.guc_log_level = 3,		/* upstream default */
	.guc_firmware_path = NULL,
	.huc_firmware_path = NULL,
	.gsc_firmware_path = NULL,
	.force_probe = CONFIG_DRM_XE_FORCE_PROBE,
	.wedged_mode = 1,		/* wedge the device on a critical error rather than keep feeding a hung GPU */
};

module_param_named(force_execlist, xe_modparam.force_execlist, bool, 0444);
MODULE_PARM_DESC(force_execlist, "Force Execlist submission");
module_param_named(probe_display, xe_modparam.probe_display, bool, 0444);
MODULE_PARM_DESC(probe_display, "Probe display hardware (default: true)");
module_param_named(vram_bar_size, xe_modparam.force_vram_bar_size, uint, 0600);
MODULE_PARM_DESC(vram_bar_size, "VRAM BAR size in MiB (firmware size retained)");
module_param_named(guc_log_level, xe_modparam.guc_log_level, int, 0600);
MODULE_PARM_DESC(guc_log_level, "GuC firmware logging level (default: 3)");
/* the string parameters (firmware paths, force_probe) keep their defaults: LinuxKPI has no string sysctl params */
module_param_named(wedged_mode, xe_modparam.wedged_mode, int, 0600);
MODULE_PARM_DESC(wedged_mode, "Wedge policy: 0 never, 1 critical errors, 2 any hang");

/* drivers only take over a display when the firmware framebuffer is not the only one wanted (nomodeset) */
static int xg_xe_check_modeset(void)
{
	return drm_firmware_drivers_only() ? -ENODEV : 0;
}

static void xg_xe_dummy_exit(void) { }

static const struct {
	int (*init)(void);
	void (*exit)(void);
} xg_xe_steps[] = {
	{ xg_xe_check_modeset, NULL },
	{ xe_hw_fence_module_init, xe_hw_fence_module_exit },
	{ xe_sched_job_module_init, xe_sched_job_module_exit },
	{ xe_register_pci_driver, xe_unregister_pci_driver },
	{ xe_observation_sysctl_register, xe_observation_sysctl_unregister },
	{ xe_pm_module_init, xg_xe_dummy_exit },
};

static int xg_xe_done;	/* how many steps succeeded, so exit undoes exactly those */

static void xg_xe_exit(void)
{
	while (xg_xe_done > 0) {
		xg_xe_done--;
		if (xg_xe_steps[xg_xe_done].exit != NULL)
			xg_xe_steps[xg_xe_done].exit();
	}
}

static int xg_xe_init(void)
{
	for (xg_xe_done = 0; xg_xe_done < (int)ARRAY_SIZE(xg_xe_steps); xg_xe_done++) {
		int err = xg_xe_steps[xg_xe_done].init();
		if (err) {
			printf("XeGfx xe: init step %d failed (%d)\n", xg_xe_done, err);
			xg_xe_exit();
			return err;
		}
	}
	return 0;
}

LKPI_DRIVER_MODULE(xe, xg_xe_init, xg_xe_exit);
MODULE_DEPEND(xe, drmn, 2, 2, 2);
MODULE_DEPEND(xe, ttm, 1, 1, 1);
MODULE_DEPEND(xe, agp, 1, 1, 1);
MODULE_DEPEND(xe, linuxkpi, 1, 1, 1);
MODULE_DEPEND(xe, linuxkpi_video, 1, 1, 1);
MODULE_DEPEND(xe, dmabuf, 1, 1, 1);
MODULE_DEPEND(xe, firmware, 1, 1, 1);
