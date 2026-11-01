# Panther Lake patches for Linux 6.14 xe

Implementation plan (task brief: `/workspace/ptl/briefs/02-ptl-patches.md`):

- [x] Generate 0100-0140 for attach, the exact 13 PCI IDs, GuC-only firmware,
  runtime PM, and PTL direct ring state.
- [x] Generate 0150-0157, preserving upstream register and KLV semantics while
  using the helpers and per-GT state present in 6.14.
- [x] Apply each patch with a dry run followed by a real application to a fresh
  scratch copy after the current `fork_xe.py`; reject fuzz and offsets.
- [x] Build the host OOB rule generator, generate the tables, review all changed
  call sites, and record sources, adaptations, omissions, and limitations here.

Only `xkpi/xe/patches/*.patch` and this document are deliverables. Work on copies
under `/tmp`; do not edit the Linux source or the concurrent build-harness files.

The source baseline is Linux v6.14 (`38fec10`),
`~/src/xe-src/linux/drivers/gpu/drm/xe`. Apply this series in filename order
with `patch -p1` inside a fresh xe directory **after** `xkpi/xe/fork_xe.py`.
No patch changes `include/drm/intel/pciids.h` or enables SR-IOV.

| Patch | Source | Effect | Adaptation to 6.14 |
| --- | --- | --- | --- |
| `0100-drmn-ptl-probe.patch` | vibe `7246d38`, xkpi `0006`; port plan M1 step 2 | Name the PCI driver `drmn`; permit PTL probe | Edit the C source directly; remove PTL's `require_force_probe`, keep default `has_sriov=false` |
| `0110-ptl-pci-ids.patch` | Mainline `36aad21d50d1` pciids.h, as recorded in the port plan | Match exactly 13 PTL IDs | Define local `XG_PTL_IDS`; replace the sole xe `INTEL_PTL_IDS` use |
| `0120-ptl-guc-only-firmware.patch` | NullMoth `d96eaca`, gpu-port/xkpi/fork_xe.py; port plan firmware policy | Select `xe/ptl_guc_70.bin`, wanted version 70.54.0, on both GTs | Two-argument `fw_def`, PTL first; omit PTL HuC and GSC entries |
| `0130-runtime-pm-always-active.patch` | vibe `7246d38`, xkpi `0011` | Make the two conditional runtime PM gets succeed with a reference | Keep callback-task early returns; use `pm_runtime_get_noresume` on the normal paths |
| `0140-ptl-disable-indirect-ring-state.patch` | Port plan B0 list; upstream alternative `f9a21696e37b` | Mitigate Wa_14025515070 with direct ring state | Clear the capability on both PTL GTs during info initialization; retain the shared Xe2 descriptors |
| `0150-wa-16023105232.patch` | `7c53ff050ba8`, drm/xe: Apply Wa_16023105232 | Set RING_PSMI_CTL bit 12 on every matching engine; ensure IDLEDLY is below MAXCNT | Reuse the existing bit definition, adapt clock initialization, add guarded 64-bit timing arithmetic |
| `0151-wa-14023061436.patch` | `92029e0baa53`, drm/xe/ptl: Apply Wa_14023061436 | Set masked MCR TDL_CHICKEN 0xe5f4 bit 12 | Existing first-render-or-compute RTP helper writes the shared RCS/CCS register |
| `0152-wa-16028005424.patch` | `9d94c1cf6ef9`, drm/xe/xe3_lpg: Apply Wa_16028005424; `de96c43a69b1`, drm/xe: Apply WA_16028005424 to Media | Set GUC_INTR_CHICKEN 0xc50c bit 1 on graphics and media GTs | Combine identical GT writes using existing RTP OR rules, preserving upstream version coverage |
| `0153-wa-13012615864.patch` | `2399bcc07c01`, drm/xe/xe3lpg: Add Wa_13012615864 | Set TDL_TSL_CHICKEN 0xe4c4 bit 6 | Reuse masked MCR definition and first-render-or-compute helper |
| `0154-wa-13011645652.patch` | `6fc957185e16`, drm/xe: Extend Wa_13011645652 to PTL-H, WCL | Enable KLV 0x9008 with existing payload 0xC40 on PTL | Extend OOB rule to 3000-3001 and retain upstream 3003; base KLV plumbing already exists |
| `0155-wa-16026007364.patch` | `d72779c29d82`, drm/xe/ptl: Apply Wa_16026007364 | Enable media-3000 KLV 0x900c with payload words `{0, 0xf}` | Add the ABI key and checked two-word ADS helper; retain GuC >= 70.47.0 guard |
| `0156-wa-14025883347.patch` | `c57db41b8d2c`, drm/xe/guc: Add Wa_14025883347 for GuC DMA failure on reset | Disable GuC idle flow and wait for ready/SRAM completion before reset | Use 6.14 `XE_WA` instead of `XE_GT_WA`; keep existing forcewake and VF ordering |
| `0157-wa-14022293748.patch` | `32af900f2c6b`, drm/xe/xe3lpg: Apply Wa_14022293748, Wa_22019794406 | Enable existing KLV 0x9009 on graphics 3000-3001 | Extend only Wa_14022293748; retain the base ADS code |
| `0158-xe3-lrc-workarounds.patch` | vibe `7246d38`, xkpi `0048` | Add LRC Wa_14026781792, Wa_22021007897 and Wa_14024681466 | Preserve render-only rules, IP 3000-3510 for the first and 3000-3005 for the other two; add the masked MCR register definition |
| `0159-guc-fence-once.patch` | vibe `7246d38`, xkpi `0049` | Use READ_ONCE/WRITE_ONCE for concurrent G2H completion | Keep the single 6.14 IRQ wait and its existing barrier; no early VF polling |

The 0158/0159 additions were integrated on 2026-11-01. All 17 patches
(0100-0159 plus 0200/0210) apply to a fresh v6.14 copy after `fork_xe.py`
without fuzz or offsets. Their generated C objects compile with the rest of
the xe C build; see [integration verification](xe-build.md#vibe-integration-verification).
Source attribution is retained in each patch. Register programming and GuC
completion on physical PTL are not established by these build checks.

The local PCI list is exactly
`B080 B081 B082 B083 B084 B085 B086 B087 B08F B090 B0A0 B0A1 B0B0`.
It excludes 6.14's `B091 B092 B0A2`. The plan records their removal by
`16016ade13f6` in v6.15 and the restoration of `B0A1` by `aee2d33da882`
in September 2026. Thus the precise 13-ID list is the recorded 2026 mainline
snapshot, rather than a claim that every ID was already present in v6.17.
Network DNS resolution was unavailable; the exact PCI history subjects,
the B083-B087/B08F addition commit, and the subject of `f9a21696e37b` could
not be independently retrieved. The relevant headers identify these limits
instead of inventing commit subjects.

All newly added rules cover B0 without a stepping restriction. In 6.14,
IP-version ranges include both endpoints; stepping ranges exclude their
right endpoint. `GRAPHICS_VERSION*` only matches the graphics GT when
standalone media exists, and `MEDIA_VERSION*` only matches the media GT.
The explicit media rule in 0152 is therefore necessary. For 0150, both the
engine and OOB rules preserve graphics 2001-3001 and media 1301-3000.
For 0151/0153, the first available RCS or CCS programs a shared reset domain;
applying the masked MCR write to each engine separately is unnecessary.
The 3003/3500 and other newer IP matches retained from upstream are dormant
where 6.14 has no corresponding GMD_ID descriptor.

For 0140, all reads of `has_indirect_ring_state` were reviewed. LRC sizing,
initialization, context-control enablement, and the per-LRC flag use the
GT capability. A clear flag selects the existing direct ring head/tail/start
accessors and skips the additional indirect page and its register programming.
`xe_lrc_indirect_ring_ggtt_addr` returns zero. Execlist uses the normal LRC
accessors; GuC ADS golden-context allocation uses `xe_gt_lrc_size`, so it
agrees with the resulting layout. No consumer needs a separate patch.

0150 deliberately corrects two hazards in the supplied upstream calculation:
the IDLEDLY multiplication could overflow 32 bits, and the corrective path
mixed nanoseconds and picoseconds. The backport compares 64-bit picoseconds
and computes `floor((MAXCNT_ps - 1) / IDLEDLY_unit_ps)`, clamped to the
21-bit field, to satisfy the strict inequality. It preserves reserved bits
and clears `INHIBIT_SWITCH_UNTIL_PREEMPTED`. Unknown clock encodings and a
zero MAXCNT produce warnings and skip adjustment; no nonnegative delay can
satisfy a strict bound of zero. Default hardware settings normally comply.
The clock base is initialized in both of 6.14's CTC branches while retaining
the existing choice of reference frequency.

Verification performed on 2026-11-01:

- All 13 patches passed a dry run followed by real application in lexical
  order after the current `fork_xe.py`: zero failures, zero fuzz, zero offsets.
- Verified fork script SHA-256:
  `fa22b74d598ac07736c3a84fe622b9608023031d4197cc33983dcacd563025fd`.
  The script was reread at the end and the scratch patches regenerated on
  its output. Its PM debug-predicate and HECI adaptations do not conflict.
- Host GCC 14.2 compiled `xe_gen_wa_oob.c` with `-O2 -Wall -Wextra`;
  the generator parsed the patched rules and emitted both C and header.
  All five referenced OOB workaround enum names were present.
- Assertions checked the exact PCI list, absence of remaining
  `INTEL_PTL_IDS` calls, PTL probe flags, GuC-only firmware entry, both GT
  capability overrides, and equality with the patch-generation tree.
- A host test compiled the actual extracted `adjust_idledly` function with
  mocked MMIO and undefined-behavior sanitization. It passed 25,165,800 cases:
  every nonzero 20-bit MAXCNT, all three distinct timestamp bases used by
  the four crystal clocks, four delay boundaries, and both inhibit states.
  It checked strict timing, reserved-bit preservation, unchanged valid
  settings, and the zero clock/MAXCNT, VF, and disabled-WA guards.
- Full xe syntax checking is left to the caller's harness as requested.
  These checks do not establish GuC 70.72.1 compatibility or physical PTL
  probe, reset, RC6, or rendering success.

The final apply log and generated/test artifacts are in
`/tmp/ptl-patches-verify-vdjjcdim/` (temporary; not build inputs).
To reproduce from the repository root:

```sh
task_scratch=$(mktemp -d /tmp/ptl-patches-check.XXXXXX)
cp -r ~/src/xe-src/linux/drivers/gpu/drm/xe "$task_scratch/xe"
python3 xkpi/xe/fork_xe.py "$task_scratch/xe"
for task_patch in "$PWD"/xkpi/xe/patches/*.patch; do
    patch -d "$task_scratch/xe" -p1 --batch --fuzz=0 --dry-run -i "$task_patch" || exit 1
    patch -d "$task_scratch/xe" -p1 --batch --fuzz=0 -i "$task_patch" || exit 1
done
gcc -O2 -Wall -Wextra -o "$task_scratch/xe_gen_wa_oob" "$task_scratch/xe/xe_gen_wa_oob.c"
"$task_scratch/xe_gen_wa_oob" "$task_scratch/xe/xe_wa_oob.rules" \
    "$task_scratch/xe_wa_oob.c" "$task_scratch/xe_wa_oob.h"
```

No requested workaround was omitted. Wa_22019794406's PTL extension is
intentionally excluded per the brief; Wa_14022293748 independently enables
their shared KLV 0x9009. Wa_14025515070 uses the requested direct-state
fallback rather than importing the newer 0x900e mechanism. Neither 0154 nor
0157 needs a base-KLV backport. The plan's later LRC WAs (vibe 0048), G2H
fence changes (0049), A0-only additions, HuC/GSC authentication, WCL device
matching, display work, and build integration are outside this brief.

The 70.54.0 entry sets 6.14's wanted GuC version. As in upstream 6.14,
an older minor version triggers a notice rather than a hard rejection;
the intended packaged firmware is 70.72.1. Packaging and hardware testing
remain the caller's integration work.
