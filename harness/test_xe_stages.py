#!/usr/bin/env python3
"""Host tests for M1 arithmetic and lifecycle contracts; no hardware claims.
Run after preparing out/xe-src with harness/score.py in xe mode.
"""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
XE = ROOT / 'out/xe-src'


def between(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


class XeStages(unittest.TestCase):
    def compile_run(self, source):
        with tempfile.TemporaryDirectory(prefix='xe-stages-') as d:
            c = pathlib.Path(d) / 'test.c'
            c.write_text(source)
            exe = str(pathlib.Path(d) / 'test')
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror',
                            '-fsanitize=undefined', str(c), '-o', exe], check=True)
            subprocess.run([exe], check=True, timeout=20)

    def test_ggtt_actual_reservation_block(self):
        block = between((XE / 'xe_ggtt.c').read_text(),
                        '\t/* Before first allocation', '\n\tif (IS_SRIOV_VF(xe)) {')
        self.compile_run('''
#include <assert.h>
#include <stdint.h>
#include <errno.h>
typedef uint64_t u64;
#define U64_MAX UINT64_MAX
#define XE_PAGE_SIZE 4096ull
#define round_down(x,a) ((x) & ~((a)-1))
#define round_up(x,a) (((x)+(a)-1) & ~((a)-1))
#define max_t(t,a,b) ((t)(a) > (t)(b) ? (t)(a) : (t)(b))
#define min_t(t,a,b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define drm_info(...) ((void)0)
struct node { u64 start, size; };
struct xe_device { int root; };
struct ggtt { void *tile; u64 size; int mm; struct node bootfb; };
static u64 off, bytes, floor_addr;
static int found, reserve_error, calls;
static void *xe_device_get_root_tile(struct xe_device *xe) { return &xe->root; }
static u64 xe_wopcm_size(struct xe_device *xe) { return floor_addr; }
static int xg_xe_bootfb_get(unsigned long long *o, unsigned long long *s) {
 *o=off; *s=bytes; return found;
}
static int drm_mm_reserve_node(int *mm, struct node *n) {
 assert(n->size && !(n->size % 4096) && !(n->start % 4096));
 calls++; return reserve_error;
}
static int run(struct xe_device *xe, struct ggtt *ggtt) { int err;
''' + block + '''
return 0; }
int main(void) {
 struct xe_device xe = {0};
 struct ggtt g = {.tile=&xe.root, .size=0xfee00000};
 floor_addr=0x200000; found=1;
 off=0x300003; bytes=4096; assert(!run(&xe,&g));
 assert(g.bootfb.start==0x300000 && g.bootfb.size==8192);
 off=0; bytes=4096; calls=0; assert(!run(&xe,&g) && !calls);
 off=floor_addr-4096; bytes=8192; assert(!run(&xe,&g));
 assert(g.bootfb.start==floor_addr && g.bootfb.size==4096);
 off=g.size-4096; bytes=8192; assert(!run(&xe,&g));
 assert(g.bootfb.start==off && g.bootfb.size==4096);
 off=g.size; calls=0; assert(!run(&xe,&g) && !calls);
 off=UINT64_MAX-1; bytes=4096; assert(run(&xe,&g)==-EINVAL);
 off=0; bytes=UINT64_MAX; assert(run(&xe,&g)==-EINVAL);
 bytes=0; assert(run(&xe,&g)==-EINVAL);
 found=-EIO; assert(run(&xe,&g)==-EIO);
 found=0; assert(!run(&xe,&g));
 found=1; off=0x300000; bytes=4096; reserve_error=-ENOSPC;
 assert(run(&xe,&g)==-ENOSPC);
 g.tile=0; assert(!run(&xe,&g));
}
''')

    def test_stolen_actual_exclusion_block(self):
        block = between((XE / 'xe_ttm_stolen_mgr.c').read_text(),
                        '\t/* BAR2 is a CPU alias', '\n\tif (!stolen_size) {')
        self.compile_run('''
#include <assert.h>
#include <stdint.h>
typedef uint64_t u64; typedef uint32_t u32;
#define U64_MAX UINT64_MAX
#define PAGE_SIZE 4096ull
#define ALIGN(x,a) (((x)+(a)-1) & ~((a)-1))
#define GENMASK_ULL(h,l) (UINT64_MAX << (l))
#define min_t(t,a,b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define IS_DGFX(xe) (0)
#define IS_SRIOV_VF(xe) (0)
#define GRAPHICS_VERx100(xe) (3000)
#define drm_err(...) ((void)0)
#define drm_info(...) ((void)0)
struct xe_device { int unused; };
struct mgr { u64 io_base, stolen_base; };
static u64 fb, bytes, remaining; static int found;
static int xg_xe_bootfb_phys_get(unsigned long long *p, unsigned long long *s) {
 *p=fb; *s=bytes; return found;
}
static void pci_read_config_dword(void *p, int reg, u32 *v) {
 *v=reg==0xc0 ? 0x80000000u : 1;
}
static void run(struct xe_device *xe, struct mgr *mgr, u64 stolen_size) {
 void *pdev=0;
''' + block + '''
remaining=stolen_size; }
int main(void) {
 struct xe_device xe={0};
 struct mgr m;
 const u64 dsm=0x180000000ull, bar=0x400800000ull;
 for (unsigned i=0; i<4096; i++) {
  m=(struct mgr){bar,0x800000};
  found=1; fb=dsm+i; bytes=8192; run(&xe,&m,0x2000000);
  u64 skip=ALIGN(i+bytes,PAGE_SIZE);
  assert(m.io_base==bar+skip && m.stolen_base==0x800000+skip);
  assert(remaining==0x2000000-skip);
 }
 m=(struct mgr){bar,0x800000}; fb=dsm-4096; bytes=8192; run(&xe,&m,0x2000000);
 assert(m.io_base==bar+4096);
 m=(struct mgr){bar,0x800000}; fb=dsm+0x2000000; run(&xe,&m,0x2000000);
 assert(m.io_base==bar && remaining==0x2000000);
 fb=dsm-8192; bytes=4096; run(&xe,&m,0x2000000); assert(m.io_base==bar);
 fb=dsm; bytes=0x4000000; run(&xe,&m,0x2000000); assert(remaining==0);
 found=0; m=(struct mgr){bar,0x800000}; run(&xe,&m,0x2000000); assert(m.io_base==bar);
}
''')

    def test_checksum_actual_hash(self):
        text = (ROOT / 'shim/src/xnu/xg_kext.cpp').read_text()
        fn = between(text, 'static uint64_t\nxg_fnv', '\nextern "C" int\nxg_xe_bootfb_checksum')
        self.compile_run('''
#include <assert.h>
#include <stdint.h>
''' + fn + '''
int main(void) {
 uint64_t basis=14695981039346656037ull;
 assert(xg_fnv(basis,0x61,1)==0xaf63dc4c8601ec8cull);
 assert(xg_fnv(basis,0x0102030405060708ull,8)!=xg_fnv(basis,0x0102030405060709ull,8));
 assert(xg_fnv(basis,0x11223344,4)!=xg_fnv(basis,0x11223345,4));
}
''')

    def test_actual_pte_translation_and_sampling(self):
        text = (ROOT / 'shim/src/xnu/xg_kext.cpp').read_text()
        fn = between(text, 'static uint64_t\nxg_fnv', '\nextern "C" int\nxg_xe_bootfb_checksum')
        sample = between(text, '  uint64_t ph = 14695981039346656037ull', '  rc = 0;')
        decode = next(line for line in text.splitlines() if 'pa[i] = (pte &' in line)
        self.compile_run('''
#include <assert.h>
#include <stdint.h>
''' + fn + '''
static uint64_t translate(uint64_t pte, uint64_t dsm) {
 unsigned long long pa[1]; unsigned i=0;
''' + decode + '''
return pa[0]; }
static uint64_t xg_boot_fb_size=8192, gsm[2]={0x1001,0x2001};
static unsigned gXeBootSurf;
static uint32_t image[2048];
static void *gXeBootPixels=image;
static void checksum(unsigned long long *ptes, unsigned long long *pixels) {
''' + sample + '''
}
int main(void) {
 const uint64_t dsm=0x180000000ull;
 assert(translate(0x800003,dsm)==dsm);
 assert(translate(0x801003,dsm)==dsm+4096);
 assert(translate(0x12345001,dsm)==0x12345000);
 unsigned long long p0,i0,p1,i1;
 checksum(&p0,&i0);
 image[1]=1; checksum(&p1,&i1); assert(p0==p1 && i0==i1);
 image[16]=1; checksum(&p1,&i1); assert(p0==p1 && i0!=i1);
 image[16]=0; image[2047]=1; checksum(&p1,&i1); assert(i0!=i1);
 image[2047]=0; gsm[1]^=1ull<<63; checksum(&p1,&i1); assert(p0!=p1 && i0==i1);
}
''')

    def test_devres_release_once(self):
        code = (ROOT / 'xkpi/xe/devres-release.inc').read_text()
        self.compile_run('''
#include <assert.h>
#include <stddef.h>
struct device { int devres_lock; };
struct devres { int linked, freed; };
struct devres_action { void *data; void (*action)(void *); };
struct record { struct devres dr; struct devres_action action; };
static struct record records[3];
static int warned, calls;
#define spin_lock(p) (assert(!*(p)), (*(p))++)
#define spin_unlock(p) (assert(*(p)==1), (*(p))--)
#define dev_warn(...) (warned++)
static void action(void *p) { calls += *(int *)p; }
static void lkpi_devm_action_release(struct device *d, void *p) {
 assert(!d->devres_lock); struct devres_action *a=p; a->action(a->data);
}
static struct devres *lkpi_devres_find_dr(struct device *d,
 void (*release)(struct device *, void *),
 int (*match)(struct device *,void *,void *),void *m) {
 assert(d->devres_lock);
 for (int i=2; i>=0; i--)
  if (records[i].dr.linked && match(d,&records[i].action,m)) return &records[i].dr;
 return NULL;
}
static void lkpi_devres_unlink_locked(struct device *d, struct devres *dr) {
 assert(d->devres_lock && dr->linked); dr->linked=0;
}
static void lkpi_devres_free_dr(struct devres *dr) {
 assert(!dr->linked && !dr->freed); dr->freed=1;
}
''' + code + '''
int main(void) {
 struct device d={0}; int one=1,two=2;
 records[0]=(struct record){{1,0},{&one,action}};
 records[1]=(struct record){{1,0},{&two,action}};
 records[2]=(struct record){{1,0},{&one,action}};
 lkpi_devm_release_action(&d,action,&one);
 assert(calls==1 && records[2].dr.freed && records[0].dr.linked);
 lkpi_devm_release_action(&d,action,&one);
 assert(calls==2 && records[0].dr.freed);
 lkpi_devm_release_action(&d,action,&one);
 assert(calls==2 && warned==1);
 lkpi_devm_release_action(&d,action,&two);
 assert(calls==4 && records[1].dr.freed && !d.devres_lock);
}
''')

    def test_sx_downgrade_atomic(self):
        code = (ROOT / 'shim/src/fbsd/xg_lock.c').read_text()
        code = code[code.index('void\nsx_downgrade_'):]
        self.compile_run('''
#include <stdint.h>
#include <assert.h>
#include <stdlib.h>
#define SX_LOCK_SHARED 1ul
#define SX_LOCK_EXCLUSIVE_WAITERS 2ul
#define SX_ONE_SHARER 8ul
#define SX_SHARERS_LOCK(n) (SX_LOCK_SHARED + SX_ONE_SHARER*(n))
#define SX_OWNER(v) ((v)&~7ul)
static void *curthread=(void *)0x1000;
struct sx { volatile uintptr_t sx_lock; int sx_recurse; };
static int locked,wakes,stores;
static void xg_sq_lock(volatile uintptr_t *p) { assert(!locked); locked=1; }
static void xg_sq_unlock(volatile uintptr_t *p) { assert(locked); locked=0; }
static void xg_wake_all(volatile uintptr_t *p) {
 assert(locked && (*p & SX_LOCK_SHARED)); wakes++;
}
static void atomic_store_rel_ptr(volatile uintptr_t *p, uintptr_t v) {
 assert(locked && v && (*p & ~7ul)==(uintptr_t)curthread); *p=v; stores++;
}
#define panic(...) abort()
''' + code + '''
int main(void) {
 struct sx s={.sx_lock=(uintptr_t)curthread};
 sx_downgrade_(&s,__FILE__,__LINE__);
 assert(s.sx_lock==SX_SHARERS_LOCK(1) && stores==1 && wakes==1);
 s.sx_lock=(uintptr_t)curthread | SX_LOCK_EXCLUSIVE_WAITERS;
 sx_downgrade_(&s,__FILE__,__LINE__);
 assert(s.sx_lock==(SX_SHARERS_LOCK(1)|SX_LOCK_EXCLUSIVE_WAITERS));
 assert(stores==2 && wakes==2 && !locked);
}
''')

    def test_wiring_and_lifetimes(self):
        ggtt = (XE / 'xe_ggtt.c').read_text()
        self.assertLess(ggtt.index('xg_xe_bootfb_get'), ggtt.index('xe_ggtt_initial_clear(struct'))
        fini = between(ggtt, 'static void ggtt_fini_early', 'static void ggtt_fini(')
        self.assertIn('drm_mm_remove_node(&ggtt->bootfb)', fini)
        self.assertNotIn('xe_ggtt_clear', fini)
        ex = (ROOT / 'xkpi/xe/src/xg_xe_exec.c').read_text()
        self.assertIn('dma_fence_wait_timeout(fence, false, min_t(unsigned long, remaining, msecs_to_jiffies(timeout_ms)))', ex)
        self.assertIn('xe_bb_free(bb, fence)', ex)
        self.assertNotIn('xe_bb_free(bb, NULL);\n   dma_fence_put', ex)
        self.assertIn('SZ_128K', ex)
        display = (XE / 'display/xe_display.c').read_text()
        probe = between(display, 'int xe_display_probe(', '\nno_display:')
        self.assertLess(probe.index('if (!xe->info.probe_display)'), probe.index('intel_display_device_probe'))
        self.assertIn('.probe_display = false', (ROOT / 'xkpi/xe/src/xg_xe_module.c').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
