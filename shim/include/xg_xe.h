/* SPDX-License-Identifier: MIT */
#ifndef XG_XE_H
#define XG_XE_H
#ifdef __cplusplus
extern "C" {
#endif
#define XG_XE_MAX_GTS 4
#define XG_XE_MAX_ENGINES 32
struct xg_xe_gt_state {
 unsigned int id, gmd, arch, release, revid, guc_major, guc_minor, guc_patch;
 int media, guc_status, running, submission, forcewake;
 char step[16];
};
struct xg_xe_state {
 int gts, engines, irq_enabled, vectors, render_minor, healthy;
 unsigned int graphics_verx100, media_verx100, platform, devid, revid;
 unsigned int graphics_gmd, media_gmd;
 char platform_name[32];
 struct xg_xe_gt_state gt[XG_XE_MAX_GTS];
};
struct xg_xe_exec {
 int engines, done, truncated;
 unsigned int irq_delta;
 char name[XG_XE_MAX_ENGINES][24];
 unsigned int submitted[XG_XE_MAX_ENGINES], seqno[XG_XE_MAX_ENGINES], completed[XG_XE_MAX_ENGINES];
 long long ns[XG_XE_MAX_ENGINES];
 int err[XG_XE_MAX_ENGINES];
};
/* GGTT byte offset and page-aligned full footprint, including PLANE_OFFSET.
 * 1 present, 0 no active pipe, negative invalid; immutable after probe. */
int xg_xe_bootfb_get(unsigned long long *offset, unsigned long long *size);
/* Physical bounding interval of all GOP pages, not a BAR address. */
int xg_xe_bootfb_phys_get(unsigned long long *phys, unsigned long long *size);
/* FNV-1a: all PTE bytes; one pixel per 64 bytes and the final pixel. */
int xg_xe_bootfb_checksum(unsigned long long *ptes, unsigned long long *pixels);
int xg_xe_state(struct xg_xe_state *st);
int xg_xe_exec(struct xg_xe_exec *ex, int timeout_ms);
#ifdef __cplusplus
}
#endif
#endif
