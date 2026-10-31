# Building xe on the XNU compatibility layer

Select one kernel mode driver with `XEGFX_KMD=i915` (default) or
`XEGFX_KMD=xe`. DRM, dma-buf, TTM and LinuxKPI still come from the existing
6.14-level drm-kmod/FreeBSD trees under `~/src/xe-src`.

```sh
export PATH=$HOME/opt/xgtc/bin:$HOME/opt/LLVM-19.1.7-Linux-X64/bin:$PATH
XEGFX_KMD=xe XEGFX_OVERLAY=$PWD/xkpi python3 harness/score.py
XEGFX_KMD=xe XEGFX_OVERLAY=$PWD/xkpi python3 harness/score.py --obj
# Regression checks for the default driver:
XEGFX_OVERLAY=$PWD/xkpi python3 harness/score.py
XEGFX_OVERLAY=$PWD/xkpi python3 harness/score.py --obj
```

`build/build_xegfx.sh` passes the selection through to the harness and linker.
The default module set is `shim,kern,lkpi,drm,dmabuf,ttm,<KMD>`. Mixed-driver
requests and invalid selections are rejected. Object builds delete the other
KMD's object directory and refresh the selected KMD's objects. The selection
is recorded in `out/kmd.txt`; the linker rejects a conflicting environment or
objects from the other driver. Run the complete object build before linking.

## Tree preparation and files

- `xkpi/xe/build.py` always copies pristine Linux v6.14 xe into `out/xe-src`,
  without tests. Nothing under `~/src` is modified. `out/i915` points to
  drm-kmod's i915 headers for xe's relative compatibility includes.
- `fork_xe.py` performs build-only text edits with exact occurrence assertions.
  These adapt BAR sizing, drm_file/TTM fields, worker user copies, clock reader
  signatures, PCI registration, PM debug/bridge checks and the ACPI include.
- `patches/*.patch` are applied with `patch -p1` in lexical order after the
  fork edits. The caller's 13 patches, 0100-0157, are included unchanged;
  their PTL behavior and sources are described in [xe-ptl-patches.md](xe-ptl-patches.md).
- The host `cc` builds `xe_gen_wa_oob.c`; each `*wa_oob.rules` generates C/H
  tables in `out/xe-gen/generated`. Linux 6.14 has `xe_wa_oob.rules` only.
- The kbuild source parser enables xe and xe display and uses the shared
  configuration for other conditions. `i915-display/` and `i915-soc/` resolve
  to drm-kmod. `exclude.txt` records every excluded file and its reason:
  Linux module glue, ftrace units and Linux VSEC telemetry.
- `include/` comes first for xe only; `xg_xe_compat.h` is force-included after
  the normal prelude. Linux uapi follows drm-kmod uapi. The target, kernel
  flags and `LINUXKPI_VERSION=61400` stay consistent with the existing build.
  The local args header extends LinuxKPI's ten-argument counter to twelve,
  which the generated RTP rules need.
- `src/xg_xe_module.c` supplies parameters and reversible init/exit steps via
  `LKPI_DRIVER_MODULE`, with drm-kmod-style module dependencies.
  `src/xg_xe_glue.c` supplies managed mutex cleanup and absent-facility semantics;
  upstream GEM TTM helpers provide mmap and dumb-offset support.
  Adapted NullMoth code records its d96eaca source in comments.

The upstream `xe_pt_walk.c`, `xe_pt_walk.h` and `xe_res_cursor.h` are used
unchanged. Upstream `xe_heci_gsc.c` is compiled rather than replaced: its only
source adaptations remove the unavailable Linux resource-tree parent and
replace the PCI BAR field access with `pci_resource_start`. Its IRQ/MEI
headers report the absent auxiliary facility. All selected xe display sources remain compiled; M1 disables runtime display
initialization with the existing 6.14 `probe_display` switch.

## Licence policy

`gpl-allow.txt` explicitly lists permitted path suffixes under the owner's xe
policy. `licence_gate` uses that list only for `XEGFX_KMD=xe`; permitted GPL
inputs appear as `allowed (owner policy)` in `out/licence.txt`. The current
object build additionally includes drm-kmod's `drm_gem_ttm_helper.c` under the
explicit xe owner policy, alongside the walker and helper headers. The i915 gate retains its previous
policy and passes with no GPL-only inputs. A direct gate check verified that
`xe_pt_walk.c` is rejected under i915 and accepted under xe.

## Firmware and verification limits

For xe, `tools/link.sh` adds `-DXEGFX_KMD_XE=1` to XNU C++ compilation,
embeds `xe/ptl_guc_70.bin` under `ptl_guc_70.bin`, and copies that blob plus
`LICENSE.xe` into Resources. i915 retains `mtl_guc_70.bin` and `LICENSE.i915`.
Both firmware entry points strip directory prefixes before lookup.

`bash -n tools/link.sh build/build_xegfx.sh` passes. The macOS link script
was not executed on Linux. These results establish compilation, not kext
linking, PTL probe, GuC operation, rendering or hardware correctness.
Worker-thread user copies return all bytes uncopied until a task-map copy
implementation exists. MEI, ftrace, VSEC, Linux sysctl tables and anonymous
OA file descriptors are unavailable; the xe headers document their answers.
HMM is disabled; userptr population explicitly returns `-EOPNOTSUPP`.
The existing shim compiler emits pointer-sign warnings.

## M1 runtime controls

Display initialization is **off by default** (`xe_modparam.probe_display=false`).
The exact LinuxKPI parameter is `compat.linuxkpi.xe_probe_display` (read-only
sysctl, tunable before module initialization). To opt into display probing,
use the boot argument `compat.linuxkpi.xe_probe_display=1`, or before stage 4:

```sh
sudo sysctl debug.xegfx_env='compat.linuxkpi.xe_probe_display=1'
```

`debug.xegfx_env` replaces the whole override string and takes precedence over
boot arguments. Set it to `compat.linuxkpi.xe_probe_display=0` for the explicit
M1 setting. Changing it after stage 4 does not reinitialize display. The xe
kext starts with an empty override string so boot arguments remain effective.
The i915 defaults and stages retain their existing settings.

The 6.14 `xe_display.c` paths were reviewed: probe-defer and feature hooks test
`xe_modparam.probe_display`; PCI info propagates it to `info.probe_display`.
`xe_display_probe` branches to `no_display` before
`intel_display_device_probe`, so no display device/fbdev takeover occurs.
Display initialization, IRQ enable/reset/handler, hotplug and PM paths return
before display MMIO when disabled. `xe_display_create` still initializes the
tracking lock and workqueue; it does not program the panel. We retain these
upstream guards rather than adding an alternative partial display path.
Stage code deliberately reads plane/pipe registers to verify firmware scanout.

### Firmware GOP preservation

`0200-m1-gop-reservations.patch` inserts a device-lifetime `drm_mm_node` in the
root GGTT during `xe_ggtt_init_early`, before **any** xe allocations and
`xe_ggtt_initial_clear`. It aligns both endpoints and reserves the intersection
with the allocator's WOPCM-to-GuC-top interval. Addresses outside that interval
are already excluded from allocation and initial clear. A conflict aborts
attach. The node is removed without clearing PTEs on managed teardown.
The log prints the original GOP range and the actual reserved intersection.

Stage 2 walks every GOP PTE. System-memory entries use their physical address;
on these integrated platforms a DM entry is relative to GSMBASE, so its
physical address is `BDSM - 8 MiB + PTE address`. BDSM comes from PCI config
0xc0/0xc4, not the BAR2 CPU alias. All pages are mapped with the shim's
`xg_vm_vmap_pa(..., VM_MEMATTR_WRITE_COMBINING)`; noncontiguous physical pages
are supported. The exported physical interval bounds all those pages.

The stolen patch compares that physical interval with physical DSM, independently
of BAR2. If they overlap, it excludes the whole DSM prefix through the last GOP
page, advances both the CPU `io_base` and GPU `stolen_base`, and shrinks the
allocator. This deliberately wastes gaps between fragmented GOP pages to keep
all of them protected. An image outside DSM changes nothing; an unknown active
GOP location disables stolen and prevents GGTT initialization. Discrete GPUs
and VFs do not use this integrated-memory exclusion.

M1 accepts an active linear, uncompressed XRGB8888 firmware surface, using
stride in 64-byte units times plane height. Tiled/compressed/other-format
surfaces, missing PTEs, zero or oversized footprints (over 256 MiB), and ranges
beyond the 4 GiB hardware GGTT fail stage 2 rather than reserving a guessed
footprint. No active pipe is explicitly skipped. Hardware validation must
confirm that the firmware uses this supported layout.

### Checksums and stages

Checksums use 64-bit FNV-1a (byte order is little endian). The PTE checksum
includes **all eight bytes of every PTE** covering the original GOP range.
The pixel checksum samples one 32-bit pixel at each 64-byte stride, plus the
final full pixel; it is a strided sample, not a full image hash. It always reads
the original physical page mapping, even if a PTE has subsequently changed.
The sample can miss unsampled pixel damage; firmware console updates can cause
real pixel changes unrelated to xe. These checks do not prove the whole
framebuffer is unchanged.

Stage 2 captures and logs both baselines. Stage 4 and every later attempted
stage log both before/after values and `unchanged` or `CHANGED/unavailable`.
Missing baselines/mappings fail verification, never report unchanged. The
existing pipe frame-counter and surface checks remain; checksum or surface
changes fail the stage even if scanout keeps counting. `XeGfxPost` publishes
the hashes and the comparison result in the IORegistry.

| Stage | xe output / action |
| --- | --- |
| 1 | Existing shim and vmap self-test |
| 2 | PCI/plane/GMD probe, original GOP GGTT/physical range, PTE/pixel baselines |
| 3 | Existing PCI/newbus/DMA initialization |
| 4 | Attach, frame/PTE/pixel checks, per-GT GuC status and loaded release version, running/submission/forcewake status, step name; raw and decoded graphics GMD at 0x132000 and media at 0x380000; driver IP versions, named platform, devid/revid, MSI vector count/IRQ enable |
| 5 | Empty MI_BATCH_BUFFER_END through a kernel exec queue per exposed hardware engine on every GT; submitted flag, fence seqno/completed seqno, nanoseconds, error; interrupt-count delta; GOP checks |
| 6 | Logs `store not implemented for xe (M1)`, returns unsupported; GOP checks |
| 7 | Accelerator-claim hook logs unsupported and never publishes `nmxgpu-claimed`; GOP checks if invoked |

Stage progression stops at unsupported stage 6, so ordinary `xegfx_stage=7`
also stops there. M1 does not claim a Metal accelerator. i915 continues to use
its existing stage-6 store and stage-7 claim hooks.

Stage 4 fails unless every GT has running GuC, enabled/non-stopped submission,
a successful GT forcewake acknowledgment, and the device has MSI/MSI-X and IRQs
enabled. Stage 5 waits at most 2 seconds per fence with a 20-second overall
submission deadline, stops on timeout, and fails on missing completions,
truncated enumeration or zero interrupt delta. The interrupt counter is the
existing IOKit shim GPU-interrupt counter (`xg_pci_irqs`); a nonzero delta is
evidence of interrupt delivery during execution, not proof every engine
completion caused its own interrupt.

Each diagnostic GT uses a fresh 128 KiB device-managed batch pool. This avoids
waiting indefinitely on the normal batch pool's unsignaled fences. It can hold
all 32 diagnostic batches even if none can yet be reused. The batch allocation
is freed against the scheduler's finished fence, including the timeout path,
and failed queues are killed asynchronously. Pools remain until device teardown;
retrying failed stage 5 allocates fresh pools. Normal kernel allocation and lock
progress still rely on the shim; the existing stage watchdog remains necessary.

### Compatibility and symbol ownership

All 13 previous xe-only unresolved APIs now have providers:

- `sx_downgrade_`: atomic exclusive-to-shared transition in the existing shim
  sleep-queue protocol; no unlock/relock gap.
- `pci_has_pme`, `pci_restore_state`, `driver_module_handler`: FreeBSD-style
  capability checks, cached PCI header/BAR/PCIe restoration, and real newbus
  driver registration/unregistration with chained events. IOPCIFamily owns MSI
  routing; M1 does not implement suspend/D3 restoration or arbitrary bridge
  reconfiguration, and module quiesce returns unsupported.
- `drm_gem_ttm_mmap`: compile drm-kmod's actual `drm_gem_ttm_helper.c` for xe,
  replacing the old local dumb-map-offset duplicate. It preserves TTM reference
  transfer semantics; userspace mmap still depends on the XNU mapping layer.
- `lkpi_devm_release_action`: `linux_devres.c` was already built. The xe build
  copies it into `out/xe-gen` and appends `devres-release.inc`, using its actual
  private callback and record layout. The matched action is unlinked under the
  devres lock, called once outside the lock, and freed, so teardown cannot call
  it again. i915 still compiles the pristine source.
- `intel_graphics_stolen_res`: initialized from stage-3 shim discovery before
  PCI registration (newer integrated platforms discover DSM directly).
- `mmu_interval_check_retry`, `mmu_notifier_range_blockable`: match the shim's
  non-invalidating, wired-map notifier model; no HMM functionality is enabled.
- `xe_hmm_userptr_populate_range`: returns `-EOPNOTSUPP`; free/unmap are empty
  because this build can never populate those resources. Do not enable
  `CONFIG_HMM_MIRROR` without implementing real invalidation and DMA mapping.
- `intel_acpi_video_register`: no-op, because XNU provides no Linux/FreeBSD
  ACPI-video registration service.

The C-only xe scoreboard has 109 unresolved symbols: 106 shared with the i915
C build and three explicitly supplied by the existing XNU kext compilation:
`_xg_pci_irqs` (`shim/src/xnu/xg_pci.cpp`), `_xg_xe_bootfb_get`, and
`_xg_xe_bootfb_phys_get` (`shim/src/xnu/xg_kext.cpp`). These are intended C/C++
bridge imports, not missing compatibility implementations. No original
xe-only unresolved API remains. A final Darwin kext link still requires macOS.

## Scoreboard (2026-11-01)

| Selection | Driver syntax | Complete syntax | Driver objects | Complete objects | C-only unresolved |
| --- | ---: | ---: | ---: | ---: | ---: |
| xe | 194/194 | 340/340 | 194/194 | 340/340 | 109 |
| i915 (default) | 276/276 | 422/422 | 276/276 | 422/422 | 109 |

The xe count grows by two files: the stage execution helper and upstream GEM
TTM helpers. Both object licence gates pass. `harness/test_xe_stages.py` runs
seven host-side tests against the generated reservation code and actual checksum
hash/sampling and PTE translation, including unaligned/overflow/out-of-range GGTT intervals and
DSM overlap/non-overlap/prefix-base accounting, plus atomic lock downgrade, devres release-once and lifetime/wiring checks.
Run it after the xe preparation/build. XNU `xg_kext.cpp` is checked both with
and without `XEGFX_KMD_XE`; the other XNU C++ units are also syntax checked.
Only the two documented older-SDK errors in `xg_pci.cpp` are excluded.
Firmware basename scanning in `xg_misc.cpp` uses a local loop because the
older public SDK does not declare `strrchr`. All 14 patches also pass a fresh
dry-run/application with zero fuzz/offsets. Both C builds have no duplicate
strong external definitions.

The final workspace is left in **i915** mode (`out/kmd.txt=i915`), with i915
objects and `out/undefined.txt`. Build logs, score JSON and undefined reports
for both selections are preserved under `out/score-{xe,i915}-{syntax,obj}.log`,
`out/score-{xe,i915}.json`, `out/licence-{xe,i915}.txt`, and
`out/undefined-{xe,i915}.txt`. `out/undefined-xe-specific.txt` lists the three
intentional XNU bridge imports. Host checks establish compilation and selected
software invariants; PTL probe, real GOP preservation, dual GuC operation,
interrupt delivery and engine completion require hardware testing.
