/* SPDX-License-Identifier: MIT */
/* Adapted from vibe-nullmoth-xe3-qemu xkpi/0033, ericek111. */
#ifndef XG_LINUX_HIGHMEM_H
#define XG_LINUX_HIGHMEM_H
#define kunmap xg_lkpi_kunmap
#define kunmap_atomic xg_lkpi_kunmap_atomic
#define kunmap_local xg_lkpi_kunmap_local
#define memcpy_to_page xg_lkpi_memcpy_to_page
#define memcpy_to_folio xg_lkpi_memcpy_to_folio
#include_next <linux/highmem.h>
#undef kunmap
#undef kunmap_atomic
#undef kunmap_local
#undef memcpy_to_page
#undef memcpy_to_folio

static inline void
kunmap(struct page *page)
{
	/* The kernel alias stays WB even when userspace/GPU mappings are WC. */
	xg_kunmap_flush(page_address(page));
	xg_lkpi_kunmap(page);
}

static inline void
kunmap_atomic(void *addr)
{
	xg_kunmap_flush(addr);
	xg_lkpi_kunmap_atomic(addr);
}

static inline void
kunmap_local(void *addr)
{
	xg_kunmap_flush(addr);
	xg_lkpi_kunmap_local(addr);
}

static inline void
memcpy_to_page(struct page *page, size_t offset, const char *from, size_t len)
{
	xg_lkpi_memcpy_to_page(page, offset, from, len);
	xg_kunmap_flush(page_address(page));
}

static inline void
memcpy_to_folio(struct folio *folio, size_t offset, const char *from, size_t len)
{
	memcpy_to_page(&folio->page, offset, from, len);
}
#endif
