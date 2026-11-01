/* SPDX-License-Identifier: MIT */
/* Adapted from vibe-nullmoth-xe3-qemu xkpi/0034, ericek111. */
#ifndef XG_LINUX_PAGE_H
#define XG_LINUX_PAGE_H
#include_next <linux/page.h>

void xg_clear_page(void *addr);
void xg_kunmap_flush(const void *addr);

#undef clear_page
#define clear_page(addr) xg_clear_page(addr)
#endif
