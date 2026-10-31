# from NullMoth nvidia-macos-driver d96eaca gpu-port/xkpi/fork_xe.py
# fork_xe.py <xe-src>: the few places where Intel's 6.14 xe needs a macOS form. Everything else is Intel's file
# unchanged. Every anchor is exact with an asserted count, each file is rewritten atomically, and the script runs
# on a fresh copy of the pristine tree each build (all-xe.sh rsyncs xe-src first).
import os, sys
root = sys.argv[1]

def edit(name, pairs):
    p = os.path.join(root, name)
    t = open(p).read()
    for old, new, n in pairs:
        assert t.count(old) == n, (name, old[:70], t.count(old))
        t = t.replace(old, new)
    open(p + ".tmp", "w").write(t)
    os.replace(p + ".tmp", p)

def cut(name, start, end, replacement=""):
    p = os.path.join(root, name)
    t = open(p).read()
    assert t.count(start) == 1 and t.count(end) == 1, (name, start[:50])
    i, j = t.index(start), t.index(end)
    assert i < j
    t = t[:i] + replacement + t[j:]
    open(p + ".tmp", "w").write(t)
    os.replace(p + ".tmp", p)

# Resizable BAR: under macOS the PCI windows belong to IOPCIFamily and are fixed by the firmware/boot loader
# (OpenCore's ResizeAppleGpuBars) before the kernel starts, so the port uses the BAR as it finds it.
cut("xe_vram.c", "static void\n_resize_bar(struct xe_device *xe, int resno, resource_size_t size)\n",
    "static bool resource_is_valid(struct pci_dev *pdev, int bar)\n")
edit("xe_vram.c", [("\tresize_vram_bar(xe);\n", "\t/* the BAR stays the size the firmware gave it (see fork_xe.py) */\n", 1)])

# drm-kmod's drm_file keeps the opener's pid as a pid_t (no struct pid), and its TTM takes no address_space
# (amdgpu passes NULL on FreeBSD for the same reason).
edit("xe_device.c", [
    ("get_pid_task(rcu_access_pointer(file->pid), PIDTYPE_PID)", "get_pid_task(file->pid, PIDTYPE_PID)", 1),
    ("\t\t\t      xe->drm.anon_inode->i_mapping,\n", "\t\t\t      NULL,\n", 1),
])

# Worker-thread user copies need the owning task's map. Our glue reports all
# bytes uncopied until that facility is implemented, rather than using current's map.
edit("xe_sync.c", [
    ("\t\tkthread_use_mm(ufence->mm);\n\t\tif (copy_to_user(ufence->addr, &ufence->value, sizeof(ufence->value)))\n",
     "\t\tif (xg_xe_mm_copy_to_user(ufence->mm, ufence->addr, &ufence->value, sizeof(ufence->value)))\n", 1),
    ("\t\tkthread_unuse_mm(ufence->mm);\n", "", 1),
])
edit("xe_vm.c", [
    ("\t\t\tkthread_use_mm(snap->snap[i].mm);\n\t\t\tif (!copy_from_user(snap->snap[i].data, userptr, snap->snap[i].len))\n",
     "\t\t\tif (!xg_xe_mm_copy_from_user(snap->snap[i].mm, snap->snap[i].data, userptr, snap->snap[i].len))\n", 1),
    ("\t\t\tkthread_unuse_mm(snap->snap[i].mm);\n", "", 1),
])

# LinuxKPI's ktime_get_*_ns return s64; xe's clock table holds u64 (*)(void). Same values, matching types.
edit("xe_query.c", [("\t\treturn &ktime_get_", "\t\treturn &xg_xe_ktime_get_", 5)])

# no SR-IOV under macOS (pci_driver has no sriov_configure in LinuxKPI); the PF path is never entered
edit("xe_pci.c", [("\t.sriov_configure = xe_pci_sriov_configure,\n", "", 1)])
# every PCI bridge under macOS is driven by IOPCIFamily, so the "unbound bridge" case cannot arise
edit("xe_pm.c", [("\tif (!bridge->driver) {\n\t\tdrm_warn(&xe->drm, \"unbounded parent pci bridge, device won't support any PM support.\\n\");\n"
                  "\t\tdevice_set_pm_not_required(&pdev->dev);\n\t}\n",
                  "\t/* the bridge is IOPCIFamily's: always bound */\n", 1)])
# acpi_target_system_state() is declared by Linux's linux/acpi.h, which xe_display.c gets indirectly on Linux only
edit("display/xe_display.c", [('#include "intel_acpi.h"\n', '#include "intel_acpi.h"\n#include <linux/acpi.h>\n', 1)])
# Only a debug-warning predicate: LinuxKPI has no runtime_status or system
# suspend target. This does not change xe runtime PM get/put policy.
edit("xe_pm.c", [(
    "\treturn dev->power.runtime_status == RPM_SUSPENDING ||\n\t\tdev->power.runtime_status == RPM_RESUMING ||\n"
    "\t\tpm_suspend_target_state != PM_SUSPEND_ON;\n",
    "\t(void)dev;\n\treturn false;\n", 1)])

# LinuxKPI exposes PCI BARs through accessors, not pci_dev.resource[]. Keep
# upstream HECI (including its failure unwinding), with only this layout adapter.
edit("xe_heci_gsc.c", [
    ("\tadev->bar.parent = &pdev->resource[0];\n", "\tadev->bar.parent = NULL; /* no Linux resource tree */\n", 1),
    ("pdev->resource[0].start", "pci_resource_start(pdev, 0)", 1),
])

print("xe fork applied")
