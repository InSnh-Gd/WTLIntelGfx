/* SPDX-License-Identifier: BSD-2-Clause
 * Appended to the unmodified FreeBSD linux_devres.c in out/xe-gen only.
 * Its private release callback and record types remain authoritative. */
static int
xg_action_match(struct device *dev, void *res, void *match)
{
 struct devres_action *a = res, *m = match;
 return a->action == m->action && a->data == m->data;
}

void
lkpi_devm_release_action(struct device *dev, void (*action)(void *), void *data)
{
 struct devres_action match = { .action = action, .data = data };
 struct devres *dr;
 spin_lock(&dev->devres_lock);
 dr = lkpi_devres_find_dr(dev, lkpi_devm_action_release, xg_action_match, &match);
 if (dr) lkpi_devres_unlink_locked(dev, dr);
 spin_unlock(&dev->devres_lock);
 if (!dr) {
  dev_warn(dev, "release of unregistered devres action\n");
  return;
 }
 lkpi_devm_action_release(dev, dr + 1);
 lkpi_devres_free_dr(dr);
}
