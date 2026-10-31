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
  `src/xg_xe_glue.c` supplies managed mutex cleanup and GEM mmap-offset lookup.
  Adapted NullMoth code records its d96eaca source in comments.

The upstream `xe_pt_walk.c`, `xe_pt_walk.h` and `xe_res_cursor.h` are used
unchanged. Upstream `xe_heci_gsc.c` is compiled rather than replaced: its only
source adaptations remove the unavailable Linux resource-tree parent and
replace the PCI BAR field access with `pci_resource_start`. Its IRQ/MEI
headers report the absent auxiliary facility. All xe display sources selected
by this configuration are compiled; this build work adds no runtime display
bypass.

## Licence policy

`gpl-allow.txt` explicitly lists permitted path suffixes under the owner's xe
policy. `licence_gate` uses that list only for `XEGFX_KMD=xe`; permitted GPL
inputs appear as `allowed (owner policy)` in `out/licence.txt`. The current
object build includes three such files: `xe_pt_walk.c`, `xe_pt_walk.h` and
drm-kmod's `include/drm/drm_gem_ttm_helper.h`. The i915 gate retains its previous
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
HMM is disabled in the existing configuration, leaving xe HMM calls unresolved.
The existing shim compiler emits pointer-sign warnings.

## Scoreboard (2026-11-01)

| Selection | Driver syntax | Complete syntax | Driver objects | Complete objects | Unresolved symbols |
| --- | ---: | ---: | ---: | ---: | ---: |
| xe | 192/192 | 338/338 | 192/192 | 338/338 | 119 |
| i915 (default) | 276/276 | 422/422 | 276/276 | 422/422 | 109 |

Both object licence gates pass. No files remain blocked by compilation.
There are no duplicate external definitions across the xe build objects.
Invalid KMD and mixed-driver requests were also checked and rejected.

The final workspace contains the xe objects, `out/kmd.txt=xe`, and xe's
`out/undefined.txt`. Results for both selections are preserved as
`out/score-{xe,i915}-{syntax,obj}.log`, `out/score-{xe,i915}.json`,
`out/licence-{xe,i915}.txt` and `out/undefined-{xe,i915}.txt`.
The 13 newly unresolved symbols compared with the i915 build are below
(all entries, fewer than the requested top 40; counts are referencing objects).
Some normally come from i915's module glue or DRM/FreeBSD compatibility code;
they are not necessarily new xe APIs. The report precedes XNU-side linking.

```text
2 _sx_downgrade_
1 _pci_has_pme
1 _drm_gem_ttm_mmap
1 _lkpi_devm_release_action
1 _intel_graphics_stolen_res
1 _driver_module_handler
1 _pci_restore_state
1 _mmu_interval_check_retry
1 _mmu_notifier_range_blockable
1 _xe_hmm_userptr_free_sg
1 _xe_hmm_userptr_populate_range
1 _xe_hmm_userptr_unmap
1 _intel_acpi_video_register
```

The comparison is also in `out/undefined-xe-specific.txt`. These runtime
interfaces and the documented absent facilities remain follow-up work.
