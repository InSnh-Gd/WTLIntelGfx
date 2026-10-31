/* HECI's Linux IRQ domain has no provider here. The GPU IRQ uses LinuxKPI's
 * PCI interrupt path; allocating a child IRQ for an absent MEI driver fails. */
#ifndef XG_XE_IRQ_H
#define XG_XE_IRQ_H
#include <linux/errno.h>
struct irq_data;
struct irq_desc;
struct irq_chip {
 const char *name;
 void (*irq_mask)(struct irq_data *);
 void (*irq_unmask)(struct irq_data *);
};
static inline void handle_simple_irq(struct irq_desc *d) { }
static inline int irq_alloc_desc(int node) { return -ENODEV; }
static inline void irq_free_desc(unsigned int irq) { }
static inline void irq_set_chip_and_handler_name(unsigned int irq, const struct irq_chip *chip,
 void (*handler)(struct irq_desc *), const char *name) { }
static inline int irq_set_chip_data(unsigned int irq, void *data) { return -ENODEV; }
static inline int generic_handle_irq(unsigned int irq) { return -ENODEV; }
#endif
