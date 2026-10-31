/* No MEI auxiliary bus on macOS. Preserve upstream HECI's device layout and
 * reject publication, so no consumer is promised a working auxiliary device. */
#ifndef XG_XE_MEI_AUX_H
#define XG_XE_MEI_AUX_H
#include <linux/device.h>
#include <linux/ioport.h>
struct auxiliary_device {
 struct device dev;
 const char *name;
 unsigned int id;
};
struct xg_xe_mei_resource {
 resource_size_t start, end;
 struct resource *parent;
 unsigned long flags;
 unsigned long desc;
};
struct mei_aux_device {
 struct auxiliary_device aux_dev;
 int irq;
 struct xg_xe_mei_resource bar;
 struct resource ext_op_mem;
 bool slow_firmware;
};
#define to_auxiliary_dev(d) container_of(d, struct auxiliary_device, dev)
#define auxiliary_dev_to_mei_aux_dev(d) container_of(d, struct mei_aux_device, aux_dev)
static inline int auxiliary_device_init(struct auxiliary_device *d) { return -ENODEV; }
static inline int auxiliary_device_add(struct auxiliary_device *d) { return -ENODEV; }
static inline void auxiliary_device_delete(struct auxiliary_device *d) { }
static inline void auxiliary_device_uninit(struct auxiliary_device *d) { }
#endif
