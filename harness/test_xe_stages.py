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

    def test_non_wb_alias_flush(self):
        text = (ROOT / 'shim/src/fbsd/xg_vm.c').read_text()
        code = between(text, 'void\nxg_kunmap_flush(', '\nvoid\npmap_copy_page(')
        header = (ROOT / 'xkpi/include/linux/highmem.h').read_text()
        wrappers = between(header, 'static inline void\nkunmap(', '\n#endif')
        self.compile_run('''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#define PAGE_SIZE 4096
#define VM_MEMATTR_WRITE_BACK 0
#define trunc_page(x) ((x) & ~(uintptr_t)(PAGE_SIZE-1))
typedef uintptr_t vm_offset_t;
struct page { struct { int pat_mode; } md; char *kva; };
typedef struct page *vm_page_t;
struct folio { struct page page; };
static char data[PAGE_SIZE] __attribute__((aligned(PAGE_SIZE)));
static struct page page;
static int flushes, unmaps, known=1;
static uintptr_t pmap_kextract(uintptr_t va) { return va; }
static vm_page_t PHYS_TO_VM_PAGE(uintptr_t pa) { return known && pa==(uintptr_t)data ? &page : NULL; }
static void xg_vm_x_flush(void *va, unsigned long n) {
 assert(va==data && n==PAGE_SIZE); flushes++;
}
static void xg_vm_zero(vm_page_t p) { memset(p->kva,0,PAGE_SIZE); }
#define bzero(p,n) memset(p,0,n)
#define PHYS_TO_DMAP(p) ((void *)(p))
#define VM_PAGE_TO_PHYS(p) ((uintptr_t)(p)->kva)
#define page_address(p) ((p)->kva)
static void xg_lkpi_kunmap(struct page *p) { unmaps++; }
static void xg_lkpi_kunmap_atomic(void *p) { unmaps++; }
static void xg_lkpi_kunmap_local(void *p) { unmaps++; }
static void xg_lkpi_memcpy_to_page(struct page *p,size_t o,const char *s,size_t n) { memcpy(p->kva+o,s,n); }
''' + code + wrappers + '''
int main(void) {
 page.kva=data;
 memset(data,1,sizeof(data)); xg_clear_page(data);
 for (int i=0;i<PAGE_SIZE;i++) assert(data[i]==0);
 assert(!flushes);
 page.md.pat_mode=1;
 kunmap(&page); kunmap_atomic(data+37); kunmap_local(data+4095);
 assert(flushes==3 && unmaps==3);
 memcpy_to_page(&page,17,"abc",3);
 assert(!memcmp(data+17,"abc",3) && flushes==4);
 struct folio folio={.page=page};
 memcpy_to_folio(&folio,20,"def",3);
 assert(!memcmp(data+20,"def",3) && flushes==5);
 xg_clear_page(data); assert(flushes==6);
 pmap_zero_page(&page); assert(flushes==7);
 page.md.pat_mode=2; xg_kunmap_flush(data); assert(flushes==8);
 known=0; xg_kunmap_flush(data); assert(flushes==8);
 xg_kunmap_flush(NULL); assert(flushes==8);
 page.md.pat_mode=0; known=1; kunmap_local(data); assert(flushes==8);
}
''')

    def test_opportunistic_allocations_skip_contiguous(self):
        code = between((ROOT / 'xkpi/src/lkpi/linux_page.c').read_text(),
                       'struct page *\nlinux_alloc_pages(', '\nstatic void\n_linux_free_kmem(')
        self.compile_run('''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
typedef unsigned gfp_t;
typedef uintptr_t vm_paddr_t;
typedef uintptr_t vm_offset_t;
struct page { int unused; };
static struct page p;
static unsigned calls, contiguous;
#define PMAP_HAS_DMAP 1
#define PAGE_SIZE 4096
#define VM_ALLOC_WIRED 1
#define VM_ALLOC_ZERO 2
#define VM_ALLOC_NORECLAIM 4
#define M_ZERO 1
#define GFP_DMA32 2
#define __GFP_NORETRY 4
#define __GFP_THISNODE 8
#define M_WAITOK 16
#define BUS_SPACE_MAXADDR UINTPTR_MAX
#define BUS_SPACE_MAXADDR_32BIT UINT32_MAX
#define PCPU_GET(x) 0
#define KASSERT(c,msg) assert(c)
static struct page *vm_page_alloc_noobj(int req) { calls++; return &p; }
static struct page *vm_page_alloc_noobj_contig(int r,unsigned long n,uintptr_t l,uintptr_t h,int a,int b,int m) {
 calls++; contiguous++; return &p;
}
#define vm_page_alloc_noobj_contig_domain(d,r,n,l,h,a,b,m) ((void)(d),vm_page_alloc_noobj_contig(r,n,l,h,a,b,m))
#define VM_MEMATTR_DEFAULT 0
static int vm_page_reclaim_contig(int r,unsigned long n,uintptr_t l,uintptr_t h,int a,int b) { return ENOMEM; }
static void vm_wait(void *p) { assert(0); }
static uintptr_t linux_alloc_kmem(unsigned f,unsigned o) { assert(0); return 0; }
static struct page *virt_to_page(void *v) { return &p; }
static void *page_address(struct page *p) { return NULL; }
''' + code + '''
int main(void) {
 for (unsigned i=1;i<=10;i++) {
  assert(!linux_alloc_pages(__GFP_NORETRY,i));
  assert(!linux_alloc_pages(__GFP_NORETRY|GFP_DMA32|M_WAITOK,i));
 }
 assert(!calls);
 assert(linux_alloc_pages(__GFP_NORETRY,0)==&p && calls==1 && !contiguous);
 assert(linux_alloc_pages(__GFP_NORETRY|GFP_DMA32,0)==&p && contiguous==1);
 assert(linux_alloc_pages(M_WAITOK,2)==&p && contiguous==2);
}
''')

    def test_xe_map_failure_and_pin_lifetime(self):
        text = (ROOT / 'xkpi/src/i915/xg_i915_map.c').read_text()
        code = between(text, 'static int\nxg_map_mmap(', '\n#endif\n\nstatic int\nxg_map_munmap(')
        code = code[code.index('#else\n') + len('#else\n'):]
        release = between(text, 'static void\nxg_map_free(', '\n#ifndef XEGFX_KMD_XE')
        self.compile_run('''
#include <assert.h>
#include <stdint.h>
#include <limits.h>
#include <stdbool.h>
#include <stdlib.h>
#include <errno.h>
#include <stddef.h>
typedef uint64_t u64; typedef uint32_t u32;
#define PAGE_SHIFT 12
#define PAGE_SIZE 4096ull
#define GFP_KERNEL 0
#define XE_BO_FLAG_SYSTEM 2
#define XE_PL_TT 1
#define DRM_XE_GEM_CPU_CACHING_WB 1
#define XG_VM_CACHE_WB 1
#define XG_VM_CACHE_WC 2
#define XG_PROT_WRITE 2
#define XEGFX_KMD_XE 1
#define DMA_RESV_USAGE_KERNEL 0
#define MAX_SCHEDULE_TIMEOUT LONG_MAX
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct list_head { int unused; };
struct drm_vma_offset_node { u64 offset; };
struct drm_gem_object { struct drm_vma_offset_node vma_node; u64 size; int refcount; void *resv,*import_attach; };
struct page { u64 pa; };
struct ttm_tt { unsigned num_pages; struct page **pages; };
struct ttm_buffer_object { struct drm_gem_object base; struct ttm_tt *ttm; void *bdev; int pin_count; };
struct xe_bo { struct ttm_buffer_object ttm; unsigned flags,cpu_caching; };
struct drm_device { void *vma_offset_manager; };
struct drm_minor { struct drm_device *dev; };
struct drm_file { struct drm_minor *minor; };
struct file { void *private_data; };
struct xg_drm_mmap { u64 offset,size; u32 prot,flags; u64 addr; };
struct xg_map { struct list_head link; void *key; u64 addr,size; void *xm; struct xe_bo *obj; };
struct ttm_operation_ctx { bool interruptible; };
static struct xe_bo bo;
static int found=1, allowed=1, lockerr, migrateerr, populateerr, mapfail, locked, maps;
static long waitret=1;
static int xg_maps_lock;
static struct list_head xg_maps;
static struct xg_map *last;
static void drm_vma_offset_lock_lookup(void *p) {}
static void drm_vma_offset_unlock_lookup(void *p) {}
static struct drm_vma_offset_node *drm_vma_offset_lookup_locked(void *p,u64 o,u64 s) { return found ? &bo.ttm.base.vma_node : NULL; }
static int drm_vma_node_is_allowed(void *n,void *p) { return allowed; }
static int kref_get_unless_zero(int *r) { if (!*r) return 0; ++*r; return 1; }
static u64 drm_vma_node_offset_addr(struct drm_vma_offset_node *n) { return n->offset; }
static struct xe_bo *gem_to_xe_bo(struct drm_gem_object *g) { return &bo; }
static int xe_bo_lock(struct xe_bo *b,bool intr) { if (!lockerr) locked++; return lockerr; }
static void xe_bo_unlock(struct xe_bo *b) { assert(locked==1); locked--; }
static int xe_bo_migrate(struct xe_bo *b,int t) { assert(locked); return migrateerr; }
static long dma_resv_wait_timeout(void *p,int u,bool intr,long timeout) { return waitret; }
static int ttm_tt_populate(void *b,struct ttm_tt *t,struct ttm_operation_ctx *c) { return populateerr; }
static void *kcalloc(unsigned n,size_t s,int f) { return calloc(n,s); }
static void *kzalloc(size_t s,int f) { return calloc(1,s); }
#define kfree free
static u64 page_to_phys(struct page *p) { return p->pa; }
static void *xg_vm_x_map_user(u64 *pa,u64 *len,unsigned n,int cache,int w,u64 *addr) {
 assert(locked && n==2 && pa[0]==0x1000 && len[0]==8192 && pa[1]==0x8000 && len[1]==4096);
 assert(cache==XG_VM_CACHE_WB && w); maps++; *addr=0x100000; return mapfail ? NULL : (void *)1;
}
static void ttm_bo_pin(struct ttm_buffer_object *b) { assert(locked); b->pin_count++; }
static void ttm_bo_unpin(struct ttm_buffer_object *b) { assert(locked && b->pin_count); b->pin_count--; }
static void xg_vm_x_release(void *xm) { assert(xm==(void *)1 && bo.ttm.pin_count); }
static void xe_bo_put(struct xe_bo *b) { b->ttm.base.refcount--; }
static void mutex_lock(int *m) {}
static void mutex_unlock(int *m) {}
static void list_add(struct list_head *l,struct list_head *h) { last=container_of(l,struct xg_map,link); }
''' + release + code + '''
int main(void) {
 struct drm_device dev={0}; struct drm_minor minor={&dev};
 struct drm_file priv={&minor}; struct file file={&priv};
 struct page p[]={{0x1000},{0x2000},{0x8000}};
 struct page *pages[]={p,p+1,p+2}; struct ttm_tt tt={3,pages};
 bo.ttm.ttm=&tt; bo.flags=XE_BO_FLAG_SYSTEM; bo.cpu_caching=1;
 bo.ttm.base.size=3*PAGE_SIZE; bo.ttm.base.refcount=1; bo.ttm.base.vma_node.offset=0x400000;
 struct xg_drm_mmap a={.offset=0x400000,.size=3*PAGE_SIZE,.prot=3};
 found=0; assert(xg_map_mmap(&file,&file,&a)==-EINVAL); found=1;
 allowed=0; assert(xg_map_mmap(&file,&file,&a)==-EACCES); allowed=1;
 a.offset++; assert(xg_map_mmap(&file,&file,&a)==-EINVAL); a.offset--;
 a.flags=1; assert(xg_map_mmap(&file,&file,&a)==-EINVAL); a.flags=0;
 a.size=UINT64_MAX & ~(PAGE_SIZE-1); assert(xg_map_mmap(&file,&file,&a)==-EINVAL); a.size=3*PAGE_SIZE;
 a.offset+=PAGE_SIZE; assert(xg_map_mmap(&file,&file,&a)==-EINVAL); a.offset-=PAGE_SIZE;
 bo.flags=0; assert(xg_map_mmap(&file,&file,&a)==-EOPNOTSUPP); bo.flags=XE_BO_FLAG_SYSTEM;
 bo.ttm.base.import_attach=&bo; assert(xg_map_mmap(&file,&file,&a)==-EOPNOTSUPP); bo.ttm.base.import_attach=NULL;
 lockerr=-EINTR; assert(xg_map_mmap(&file,&file,&a)==-EINTR); lockerr=0;
 migrateerr=-ENOMEM; assert(xg_map_mmap(&file,&file,&a)==-ENOMEM); migrateerr=0;
 waitret=-EINTR; assert(xg_map_mmap(&file,&file,&a)==-EINTR); waitret=1;
 populateerr=-ENOMEM; assert(xg_map_mmap(&file,&file,&a)==-ENOMEM); populateerr=0;
 pages[1]=NULL; assert(xg_map_mmap(&file,&file,&a)==-ENODEV); pages[1]=p+1;
 assert(!locked && bo.ttm.base.refcount==1 && !bo.ttm.pin_count);
 mapfail=1; assert(xg_map_mmap(&file,&file,&a)==-ENOMEM);
 assert(!locked && bo.ttm.base.refcount==1 && !bo.ttm.pin_count);
 mapfail=0; assert(!xg_map_mmap(&file,&file,&a));
 assert(!locked && bo.ttm.base.refcount==2 && bo.ttm.pin_count==1);
 assert(last && last->key==&file && last->obj==&bo && a.addr==last->addr && maps==2);
 xg_map_free(last);
 assert(!locked && bo.ttm.base.refcount==1 && !bo.ttm.pin_count);
}
''')

    def test_mapping_cleanup_at_final_file_drop(self):
        text = (ROOT / 'shim/src/fbsd/xg_fd.c').read_text()
        code = between(text, 'int\n_fdrop(', '\n/*\n * Private descriptor tables')
        close = between(text, 'xg_fd_dev_close(', '\nint\nxg_fd_inst_fget(')
        self.assertNotIn('xg_fd_map_close(fp)', close)
        self.compile_run('''
#include <assert.h>
#include <stdlib.h>
struct file { unsigned f_count; };
struct thread { int unused; };
static int xg_fd_openfiles=1, released, closed;
#define KASSERT(c,msg) assert(c)
#define M_XGFD 0
static unsigned refcount_load(unsigned *p) { return *p; }
static void atomic_subtract_int(int *p,int n) { *p-=n; }
static void release_maps(void *p) { assert(!closed); released++; }
void (*xg_fd_map_close)(void *)=release_maps;
static int fo_close(struct file *p,struct thread *t) { assert(released==1); closed++; return 0; }
#define free(p,t) free(p)
''' + code + '''
int main(void) {
 struct file *fp=calloc(1,sizeof(*fp)); struct thread td={0};
 assert(!_fdrop(fp,&td));
 assert(released==1 && closed==1 && !xg_fd_openfiles);
}
''')

    def test_bootfb_actual_layout(self):
        text = (ROOT / 'shim/src/xnu/xg_kext.cpp').read_text()
        fn = between(text, 'static int\nxg_xe_bootfb_layout(',
                     '\n/* Stage 2 only.')
        self.compile_run('''
#include <assert.h>
#include <stdint.h>
#include <errno.h>
''' + fn + '''
int main(void) {
 uint64_t size;
 const uint32_t ctl = (1u << 31) | (4u << 24);
 assert(!xg_xe_bootfb_layout(ctl,120,1079u<<16,0,0x200000,&size));
 assert(size==((7680ull*1080+4095)&~4095ull));
 assert(!xg_xe_bootfb_layout(ctl,120,1079u<<16,(17u<<16)|33,0x200000,&size));
 assert(size==((1097ull*7680+33*4+4095)&~4095ull));
 /* Bit 11 of stride must survive; reserved offset bits must not. */
 assert(!xg_xe_bootfb_layout(ctl,0x801,0,0xe000e000u,0,&size));
 assert(size==((0x801ull*64+4095)&~4095ull));
 assert(!xg_xe_bootfb_layout(ctl,1,0,(8191u<<16)|8191,0,&size));
 assert(size==((8192ull*64+8191*4+4095)&~4095ull));
 /* X offset can require one more page after a page-aligned row span. */
 assert(!xg_xe_bootfb_layout(ctl,64,0,1,0,&size) && size==8192);
 for (unsigned i=0;i<32;i++) {
  uint32_t bit=1u<<i;
  if (bit & ((3u<<0)|(1u<<8)|(7u<<10)|(1u<<15)|(1u<<4)))
   assert(xg_xe_bootfb_layout(ctl|bit,120,0,0,0,&size)==-EOPNOTSUPP);
 }
 assert(xg_xe_bootfb_layout(ctl|(1u<<23),120,0,0,0,&size)==-EOPNOTSUPP);
 assert(xg_xe_bootfb_layout(ctl&~(1u<<31),120,0,0,0,&size)==-EOPNOTSUPP);
 assert(xg_xe_bootfb_layout(ctl,0,0,0,0,&size)==-EINVAL);
 assert(xg_xe_bootfb_layout(ctl,0xfff,8191u<<16,8191u<<16,0,&size)==-EOVERFLOW);
 assert(xg_xe_bootfb_layout(ctl,64,0,1,0xfffff000u,&size)==-EOVERFLOW);
 assert(!xg_xe_bootfb_layout(ctl,64,0,0,0xfffff000u,&size) && size==4096);
}
''')

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
        self.assertNotIn('xe_exec_queue_kill(q)', ex)
        self.assertIn('if (ex->err[n]) q->ops->kill(q);', ex)
        self.assertIn('state->pending = dma_fence_get(fence)', ex)
        self.assertLess(ex.index('xg_xe_exec_pool_get(gt)'),
                        ex.index('q = xe_exec_queue_create'))
        self.assertIn('g->gmd = xe_mmio_read32(&gt->mmio, GMD_ID)', ex)
        self.assertNotIn('XE_REG(0x132000)', ex)
        self.assertNotIn('XE_REG(0x380000)', ex)
        display = (XE / 'display/xe_display.c').read_text()
        probe = between(display, 'int xe_display_probe(', '\nno_display:')
        self.assertLess(probe.index('if (!xe->info.probe_display)'), probe.index('intel_display_device_probe'))
        self.assertIn('.probe_display = false', (ROOT / 'xkpi/xe/src/xg_xe_module.c').read_text())

    def test_exec_pool_actual_reuse(self):
        text = (ROOT / 'xkpi/xe/src/xg_xe_exec.c').read_text()
        code = between(text, 'struct xg_xe_exec_pool {',
                       '\nstatic struct xe_bb *xg_xe_bb_new')
        self.compile_run('''
#include <assert.h>
#include <stdlib.h>
#include <errno.h>
#include <stdint.h>
#define GFP_KERNEL 0
#define SZ_128K (128*1024)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define ERR_CAST(p) ((void *)(p))
struct dma_fence { int signaled, refs; };
struct xe_sa_manager { int unused; };
struct xg_xe_exec_pool;
struct xe_gt { struct xg_xe_exec_pool *m1_exec; };
struct drm_device { int unused; };
struct xe_device { struct drm_device drm; };
static struct xe_device xe;
static int allocs, managers, fail_manager;
static void (*release_state)(struct drm_device *,void *);
static void *release_arg;
static struct xe_device *gt_to_xe(struct xe_gt *gt) { return &xe; }
static void *gt_to_tile(struct xe_gt *gt) { return gt; }
static void *drmm_kzalloc(struct drm_device *drm,size_t n,int flags) { allocs++; return calloc(1,n); }
static int drmm_add_action_or_reset(struct drm_device *drm,void (*fn)(struct drm_device *,void *),void *arg) {
 release_state=fn; release_arg=arg; return 0;
}
static struct xe_sa_manager manager;
static struct xe_sa_manager *xe_sa_bo_manager_init(void *tile,unsigned n,unsigned align) {
 assert(n==SZ_128K && align==64); managers++;
 return fail_manager ? ERR_PTR(-ENOMEM) : &manager;
}
static int dma_fence_is_signaled(struct dma_fence *f) { return f->signaled; }
static void dma_fence_put(struct dma_fence *f) { if(f) { assert(f->refs>0); f->refs--; } }
''' + code + '''
int main(void) {
 struct xe_gt gt={0}, failed={0};
 struct dma_fence f={0,1};
 struct xg_xe_exec_pool *s=xg_xe_exec_pool_get(&gt);
 assert(!IS_ERR(s) && allocs==1 && managers==1);
 assert(xg_xe_exec_pool_get(&gt)==s && managers==1);
 s->pending=&f;
 for(int i=0;i<100;i++) assert(PTR_ERR(xg_xe_exec_pool_get(&gt))==-EBUSY);
 assert(managers==1 && allocs==1 && f.refs==1);
 f.signaled=1;
 assert(xg_xe_exec_pool_get(&gt)==s && !s->pending && f.refs==0);
 assert(managers==1);
 f.refs=1; s->pending=&f;
 release_state(&xe.drm,release_arg);
 assert(f.refs==0); free(s);
 fail_manager=1;
 assert(PTR_ERR(xg_xe_exec_pool_get(&failed))==-ENOMEM);
 for(int i=0;i<100;i++) assert(PTR_ERR(xg_xe_exec_pool_get(&failed))==-ENOMEM);
 assert(managers==2 && allocs==2);
 release_state(&xe.drm,release_arg); free(failed.m1_exec);
}
''')

    def test_kernel_queue_actual_error_cleanup(self):
        text = (ROOT / 'xkpi/xe/src/xg_xe_exec.c').read_text()
        cleanup = between(text, '   /* The common kill helper', '\nreport:')
        self.compile_run('''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
struct queue;
struct ops { void (*kill)(struct queue *); };
struct queue { void *vm; struct ops *ops; int refs, kills; };
struct result { int err[1]; };
static void kill(struct queue *q) { assert(!q->vm && q->refs==1); q->kills++; }
static void xe_exec_queue_put(struct queue *q) { assert(q->refs==1); q->refs--; }
static void cleanup(struct queue *q,int err,int allocation_failed) {
 struct result result={{err}}, *ex=&result; int n=0;
 if(allocation_failed) goto put_q;
''' + cleanup + '''
}
int main(void) {
 struct ops ops={kill};
 const int errors[]={0,-ETIMEDOUT,-EIO};
 for(int i=0;i<3;i++) {
  struct queue q={NULL,&ops,1,0}; cleanup(&q,errors[i],0);
  assert(q.refs==0 && q.kills==(errors[i]!=0));
 }
 struct queue q={NULL,&ops,1,0}; cleanup(&q,-ENOMEM,1);
 assert(q.refs==0 && q.kills==0);
}
''')

    def test_actual_gmd_registers_and_decode(self):
        regs = (XE / 'regs/xe_gt_regs.h').read_text()
        definitions = '\n'.join(line for line in regs.splitlines()
                                if line.startswith('#define MEDIA_GT_GSI_OFFSET') or
                                line.startswith('#define GMD_ID\t') or
                                line.startswith('#define   GMD_ID_'))
        self.compile_run('''
#include <assert.h>
#include <stdint.h>
#define XE_REG(v) (v)
#define REG_GENMASK(h,l) ((UINT32_MAX >> (31-(h))) & (UINT32_MAX << (l)))
#define REG_FIELD_GET(mask,v) (((v)&(mask)) >> __builtin_ctz(mask))
''' + definitions + '''
int main(void) {
 assert(GMD_ID==0xd8c && GMD_ID+MEDIA_GT_GSI_OFFSET==0x380d8c);
 for(unsigned release=0;release<2;release++) {
  uint32_t gmd=(30u<<22)|(release<<14)|4u;
  assert(REG_FIELD_GET(GMD_ID_ARCH_MASK,gmd)==30);
  assert(REG_FIELD_GET(GMD_ID_RELEASE_MASK,gmd)==release);
  assert(REG_FIELD_GET(GMD_ID_REVID,gmd)==4);
 }
}
''')
        kext = (ROOT / 'shim/src/xnu/xg_kext.cpp').read_text()
        self.assertIn('{ "gmd-id-graphics", 0xd8c }', kext)
        self.assertIn('{ "gmd-id-media", 0x380d8c }', kext)


if __name__ == '__main__':
    unittest.main(verbosity=2)
