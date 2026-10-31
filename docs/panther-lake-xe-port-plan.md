# Panther Lake（Xe3）裸机 xe 移植计划

阶段：调研和计划。本文不交付可运行的驱动。

目标是在现有 XeGfx 上，把底层从 i915 换成 Linux 的 xe，让 Panther Lake 核显（Xe3，例如 Arc B390）在物理机上完成：probe、GuC 加载、ANV + Metal、桌面合成。优先级按技术依赖和最快能点亮来排。能用的 NullMoth / vibe-nullmoth 改动直接移植到本仓库对应文件，不另起一套实现。

## 1. 来源

三处都核对过，以仓库里实际的树和补丁为准。

| 是什么 | 在哪 | 提交 |
|---|---|---|
| xe 内核移植的底（NMXGPU） | [nullmoth/nvidia-macos-driver](https://github.com/nullmoth/nvidia-macos-driver) 的 `gpu-port/xkpi` | `d96eaca`（2026-10-15，"Driver and Mac app 2.0.2"） |
| QEMU SR-IOV VF 上跑通 WindowServer、Metal 的补丁 | [ericek111/vibe-nullmoth-xe3-qemu](https://github.com/ericek111/vibe-nullmoth-xe3-qemu) | `7246d38`（2026-10-18，initial commit） |
| 同一套补丁的副本 | [VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics](https://github.com/VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics) 的 `NullMoth-Xe/` | 与 vibe 仓库的 README 和全部 115 个 patch 逐字节相同 |

不存在名为 NullMoth-Xe 的独立上游仓库。xe 驱动在 NullMoth 的 `gpu-port/xkpi` 里，由 `all-xe.sh` 从 Linux 6.14 编出 NMXGPU。当前 HEAD `ceba63c`（2026-10-30）已经没有 `gpu-port/` 目录，基线锁 `d96eaca`。

vibe 的补丁打在 `d96eaca` 上：xkpi 50 个、nvidia-macos-driver 47 个，另有 drm-kmod 1、libdrm 5、Mesa 8、QEMU 4。逐项分类在 [nullmoth-patch-triage.md](nullmoth-patch-triage.md)。

`d96eaca` 的 `gpu-port/README.md` 写明 NMXGPU 当时还没有在硬件上加载过。VF 上的结果来自 vibe 的 README，不是 NullMoth 自己的声明。

上游事实另有一份对照：Linux `36aad21d50d1`（2026-10-30，7.3）和 linux-firmware `bda6eccc3a8f`（2026-10-31）。6.14 的行为用 tag `v6.14` 的 `drivers/gpu/drm/xe/xe_pci.c` 核对过，和主线不一样的地方下面单独写。

## 2. 本仓库现在的路径

```
Metal / WindowServer
plugin/                         Metal → Vulkan（ANV）
Mesa ANV + libdrm               userland/patches/
────────────────────────────────────────────────
/dev/dri 或 IOKit user client   shim/src/xnu/xg_fd.cpp，sandbox 走 IOKit
drm、TTM、dma-buf、i915          drm-kmod，源码几乎不改
LinuxKPI                        FreeBSD，本仓库只覆盖 linux_page.c、linux_schedule.c
FreeBSD API on XNU              shim/src/fbsd、shim/src/xnu
XNU：IOKit、Mach
```

构建入口是 `build/build_xegfx.sh`，`XEGFX_OVERLAY=xkpi`。`harness/score.py` 的模块只有 `shim,kern,lkpi,drm,dmabuf,ttm,i915`。没有 xe。drm-kmod 的基线是 `c16de0f`（Linux 6.14 这一档）。xe 不在 drm-kmod 里，NullMoth 是从 Linux 6.14 源码树另拷的。

i915 能接到 ANV 和 Metal，靠的是这几处胶水，换成 xe 时都要有对应物：

| 现在（i915） | 作用 | xe 落点 |
|---|---|---|
| `shim/src/xnu/xg_kext.cpp` 默认环境 `i915_disable_display=1`、`i915_enable_guc=3` | 显示先关，GuC 强制打开 | xe 用自己的参数。`enable_guc` 是 i915 的。PTL 在 6.14 上还要处理 `require_force_probe` |
| stage 4 之后 `xg_i915_state` / `xg_i915_exec`（`xkpi/src/i915/`） | GuC 是否在跑、每个引擎一次提交 | 同样的 stage 检查改问 xe：GT0、GT1 的 GuC |
| `xkpi/src/i915/xg_i915_map.c`，ioctl `'N' 0x40/0x41` | XNU 不能对设备做 mmap(2)，GEM 用 ioctl 映射 | xe 的 BO 走同一组 ioctl，或 ANV 的 xe backend 调现有的 `drmNmxMmap` |
| `xkpi/src/i915/xg_drm_sync.c`，`'N' 0x42/0x43` | dma-buf / sync_file 的替代 | 与 KMD 无关，可复用 |
| `xkpi/src/i915/i915_gem_stolen.c` 的 `xg_stolen_start()` | 固件画面还在 stolen 里，分配器从它后面开始 | xe 的 stolen / GGTT 分配做同样的预留 |
| `xkpi/src/i915/intel_display_device.c` 的 `i915_xegfx_no_display` | `disable_display` 仍会摸连接器 | xe 的 display 初始化默认先别动 GOP 扫描 |
| `shim` 的 `request_firmware` | 要 `i915/mtl_guc_70.bin`，再退回文件名，从 kext Resources 加载 | xe 要 `xe/ptl_guc_70.bin`，同一套剥前缀 |

设备匹配在 `shim/src/fbsd/xg_pci.c`：给显示功能挂 `vgapci`，下面再挂 `drmn`。FreeBSD LinuxKPI 只把名为 `drmn` 的 PCI driver 挂到 `vgapci`。drm-kmod 里的 i915 已经改名 `drmn`。xe 自己的 `pci_driver.name` 在 6.14 里是 `DRIVER_NAME`（`"xe"`），不改名就 attach 不上。vibe 的 xkpi `0006` 就是改这个名字。

两个驱动都叫 `drmn` 再链进同一个 kext，后注册的会盖住先注册的。Arrow Lake 的 i915 路径还要留着。第一阶段用编译开关只链其中一个，或者 xe 单独一个 kext。

中断：`docs/xg_pci.md` 写了 `pci_alloc_msi` 在向量不够时调用 `configureInterrupts()`。PF 有 INTx。vibe `0026` 是因为 VF 没有传统中断线。点亮不必再移植这份。

电源：本 kext 没有 `registerPowerDriver` / `setPowerState`。vibe `0031`（把第一次 power-on 当成 resume，导致 GuC submission 计数变成 -1）对当前结构不发生。以后若把 IOKit 电源转成 `device_resume`，再按那份补丁处理。

临界区：`shim/src/fbsd/xg_kern.c` 的 `critical_enter_KBI` 计在 `td_critnest` 上，是每线程的。`spinlock_enter` 用 `td_md.md_spinlock_count` 嵌套，中断标志在最外层恢复。`shim/include/sys/sched.h` 把 `sched_pin` 绑到当前 CPU，注释写明否则 RCU 读端会迁核。vibe `0020`、`0023`、`0039`、`0040` 修的是 NullMoth `bsdcompat` 里 per-CPU 计数和 per-CPU RCU 记录，本仓库这套已经不是那个结构，不把 `nmx_kernel.c` / `nmx_lock.c` 盖上来。

页映射：`xkpi/src/lkpi/linux_page.c` 的 `vmap` 走到 `xg_vm_vmap_pa()`。`shim/src/xnu/xg_vm.cpp` 的 `xg_vm_map_ranges` 用一次 `IOMemoryDescriptor::withAddressRanges`。vibe `0012` 的结论是：带 `kIOMemoryTypePhysical64` 的多段 descriptor 只映射第一段物理连续区，`xe_lrc_init` 在第 9 页的 BO 上 fault。本仓库的 stage 1 自测只映射连续的两页。这是点亮前要做的实验，失败就把 `0012` 的做法（一段一个 descriptor，再用 `IOMultiMemoryDescriptor` 接起来）接到 `xg_vm.cpp`。

等待超时：`xg_fd.cpp` 的 `xg_fd_ioctl_errno` 已经把 `ETIMEDOUT` 转成 Darwin 的 `ETIME`（101）。vibe `0025` 不必再移植。

用户态：`userland/BUILD.md` 把 Mesa 锁在 `bffd91947ef`（26.3.0-devel，2026-10-10），libdrm 锁在 `b97cbde`。`patches/mesa-xegfx.patch` 只改了 `src/intel/vulkan/i915/anv_kmd_backend.c` 的 mmap。芯片矩阵里 PTL `0xb080` 能 `vkCreateDevice`，走的是 noop shim 的 i915 uAPI，不是 xe uAPI。真机要补 xe backend。

桌面：`kexts/XeGfxAccel` 把合成结果送到面板，`kexts/XeGfxIntelFB` / `NMIntelFB` 和 `XeGfxAGDC` 管固件帧缓冲和 AGDC。Arrow Lake 上 WindowServer 已经在 Intel GPU 上合成。这条路径是 PTL 第一帧的面板侧，不换成 virtio。

## 3. 直接拿过来的代码，落在哪

NullMoth 的层和本仓库不是同一棵树。`d96eaca` 的 `gpu-port/xkpi/bsdcompat` 是他们自己的 FreeBSD API；本仓库是 `shim/src/fbsd`。`override/xe` 是他们替换掉的 xe 文件。整目录覆盖会和现有 i915 路径、`xg_sched`、`xg_vm` 冲突。

移植方式：

- 改 xe 源码的（`fork_xe.py` 里的编辑，以及 vibe 打在 `fork_xe.py` 上的 `0006`、`0048`、`0049`）：把同样的文本改动做到我们编译的那份 6.14 xe 上。`fork_xe.py` 可以搬进构建，作为对上游树的补丁脚本。
- 改 XNU 映射、cdev、页的：改 `shim/` 和 `xkpi/src/lkpi/`，按补丁里的行为改，不替换整个 `nmx_*.c`。
- 改 ANV / libdrm / plugin 的：打进 `userland/patches/` 和 `plugin/`。本仓库已有的 i915 侧改动保留。

`d96eaca` 的 `all-xe.sh` 会从 xe 树里拿掉 `xe_pt_walk.c`、`xe_pt_walk.h`、`xe_res_cursor.h`、`xe_trace*`、`xe_vsec.*`、`xe_module.c`、`xe_heci_gsc.c`，再编 `override/xe` 里的替代。点亮路径不跟着做这套替换：

- `xe_pt_walk.c` / `.h`、`xe_res_cursor.h` 直接编 Linux 6.14 的原文件。vibe `0016` 修的是 NullMoth 那份 walker（回调拿到的 child 是槽位指针，`pt_post_descend` 在没有下降时也跑）。上游文件若编不过，再改用 `d96eaca` 的 `override/xe` 并带上 `0016`。
- `xe_module.c` 是 Linux 的 module 入口。本 kext 用 SYSINIT，和 i915 一样另写一份注册，文件本身可以留在树里不编。
- `xe_heci_gsc.c` 直接编。它在 Linux 上创建给 MEI 绑定的辅助设备。macOS 没有 MEI 驱动，第一帧不依赖有人绑定它。HuC 认证以后再补 GSC proxy。
- `xe_trace*`、`xe_vsec.*`：6.14 的调用点如果在没有 tracepoint 的 LinuxKPI 上编不过，用空的头文件让引用通过。`xe_vsec` 是 PMT telemetry，点亮不调用它。
- `xe_i2c`、`xe_amc` 在 Linux 6.14 里不存在（tag `v6.14` 上这两个路径是 404）。点亮留在 6.14，不处理它们。

`fork_xe.py`（`d96eaca`）里点亮要用的编辑：

- `xe_pci.c` 去掉 `.sriov_configure`（LinuxKPI 的 `pci_driver` 没有这个回调）。这和 vibe `0001` 不是一回事。`0001` 把 `has_sriov` 设为真，VF 才会走 VF 探针。裸机 PF 保持 6.14 的默认，`has_sriov` 关闭，本地加载 GuC。
- `xe_uc_fw.c` 给 `PANTHERLAKE` 只加上 GuC，不定义 HuC 的 fw_def，并且明确不加入 GSC。原补丁把 GuC 下限写成和 LNL/BMG 一样的 70.29.2。点亮时下限改成主线现在的 70.54.0，链进去的文件用 linux-firmware 里的 70.72.1。M1 定义了 HuC 路径但文件缺失会让 probe 失败，认证失败会走到 `xe_gt_assert`，所以 HuC/GSC 认证留到后期。
- BAR 不在驱动里 resize，沿用固件 / OpenCore 已经设好的窗口。
- runtime PM 那几处是“macOS 上没有 per-device RPM 状态”。和 vibe `0011` 一起看：若 `pm_runtime_get_if_active` 仍是失败桩，G2H 会被丢掉，先修这个。

## 4. 设备和固件

### PCI ID

6.14 `include/drm/intel/pciids.h` 的 `INTEL_PTL_IDS`（10 个）：`B080 B081 B082 B090 B091 B092 B0A0 B0A1 B0A2 B0B0`。

主线 `36aad21` 的 `INTEL_PTL_IDS`（13 个，调研笔记对到 pciids.h 870–885 行）：`B080 B081 B082 B083 B084 B085 B086 B087 B08F B090 B0A0 B0A1 B0B0`。`B091`、`B092`、`B0A2` 已经从主线表里删除（`16016ade13f6` 在 v6.15 删掉这批预生产 ID）。`B0A1` 是 `aee2d33da882` 在 2026-09 重新加回的，v7.2 里还没有。Wildcat Lake `FD80` / `FD81` 在主线 `xe_pci.c` 里也指向 `ptl_desc`，不在这次点亮范围里。

Mesa `bffd919` 的 `include/pci_ids/iris_pci_ids.h` 有 `B080`–`B087`、`B08F`、`B090`、`B0A0`、`B0B0`，没有 `B0A1`。`0xb080` 的名字是 `Intel(R) Arc(tm) B390`。

点亮先覆盖 `B080` 和实机 `B082`，这两个 ID 在 6.14 和主线里都有，不受影响。6.14 缺 `B083`–`B087` 和 `B08F`，等于少了一半 B390/B370 零售 SKU，还带着已删除的 `B091`/`B092`/`B0A2`。M1 把 `ptl_ids` 和 Info.plist 匹配表按主线的 13 个 ID 补齐，删掉 `B091`、`B092`、`B0A2`，不手写第三张表。

Framework 13 的实机（[issue #11](https://github.com/watchthelight-labs/WTLIntelGfx/issues/11)）是 `8086:b082` rev 04，Linux xe 报：

- SR-IOV PF mode，display 30.00 stepping B0
- `graphics_verx100 3000`，`media_verx100 3000`，stepping G:B0 M:B0
- `has_flat_ccs yes`
- GT0：`rcs0 bcs0 bcs8 ccs0`（ccs1–3 fused off），GuC `xe/ptl_guc_70.bin` 70.72.1
- GT1：`vcs0 vecs0 gsccs0`，GuC 70.72.1，HuC `xe/ptl_huc.bin` 10.3.3，GSC `xe/ptl_gsc_1.bin` 105.0.2.1397
- DMC `i915/xe3lpd_dmc.bin` v2.36
- `mei_gsc_proxy` 绑在 `0000:00:16.0`
- 日志里有 `Selective fetch area calculation failed in pipe A`，`Allocated fbdev into stolen`

`B080` 的 GMD_ID 没有这份实机日志。Intel 的表把 B080/B082/B084/B086 都列为 Arc B390、12 Xe 核。下面按 B082 的 30.00 来做，换 ID 时以读到的 GMD_ID 为准。

### 6.14 的 `ptl_desc` 实际有什么

tag `v6.14` 的 `xe_pci.c`：

```c
static const struct xe_device_desc ptl_desc = {
	PLATFORM(PANTHERLAKE),
	.has_display = true,
	.require_force_probe = true,
};
```

GMD_ID `3000` 和 `3001` 映射到 `graphics_xe2`，名字字符串是 `"Xe2_LPG / Xe2_HPG / Xe3_LPG"`。`XE2_GFX_FEATURES` 里已经有 `has_flat_ccs = 1`、`dma_mask_size = 46`、`va_bits = 48`、`vm_max_level = 4`。媒体 GMD_ID `3000` 映射到 `media_xe2`，引擎掩码含 `GSCCS0`。

所以在 6.14 上，B082 这种 30.00 的核显会从图形 IP 描述拿到 flat CCS，不是从 `ptl_desc`。主线 7.3 把 `has_flat_ccs`、`has_sriov` 写在 `ptl_desc` 上，图形 IP 还多了 30.03 / 30.04 / 30.05，其中 30.03 是 WCL，30.04/30.05 是 xe3p 系列，都不是 PTL，和 PTL 点亮无关。B082 实测 graphics/media 都是 30.00，正好落在 6.14 的 3000/3001 表里。B080 按 SKU 推断也是 30.00，等实机读 GMD_ID 确认。基线是否上调看的是 WA 缺失和固件处理（M1 的回移清单），不是这张 IP 表；中期目标把 xe 对齐到 v7.2。

`require_force_probe` 在 6.14 上还在。不关的话，驱动认到 ID 也会拒绝 probe。主线从 6.17 起拿掉了这个标志（`94de1dfd4729`）。我们编 6.14，就在 `ptl_desc` 里关掉，或给一个 `xe.force_probe` tunable，默认放行 PTL。

### 固件

主线 `xe_uc_fw.c`（`36aad21`）和 issue #11 的 dmesg：

| 用途 | 驱动里的路径 | 版本 | 点亮 |
|---|---|---|---|
| GuC | `xe/ptl_guc_70.bin` | 下限 70.54.0；linux-firmware 与实机都是 70.72.1 | 要。GT0、GT1 各加载一份 |
| HuC | `xe/ptl_huc.bin` | 实机 10.3.3 | M1 不定义 fw_def，状态保持 `NOT_SUPPORTED`，渲染不靠它。认证和 GSC 留到后期 |
| GSC | `xe/ptl_gsc_1.bin` | 下限 major 105；实机 105.0.2.1397，运行 `cv105.1.0` | 第一帧不要。HuC 认证和 PXP 需要，还要 MEI GSC proxy |
| DMC（display 30.00） | `i915/xe3lpd_dmc.bin` | 实机 v2.36 | 第一帧不要。走固件帧缓冲拷贝时 GOP 已经点着面板。xe 自己做 modeset 时再加载 |
| DMC（display 30.02，WCL） | `i915/xe3lpd_3002_dmc.bin` | release 31 | 这次不覆盖 WCL |

kext 里放文件名本身（`ptl_guc_70.bin`），和现在的 `mtl_guc_70.bin` 一样。`request_firmware` 先试完整相对路径，再试去掉目录的名字。

### Mesa

`bffd919` 的 `VERSION` 是 `26.3.0-devel`，高于 25.2。同一提交的 `intel_device_info_ptl` 是 `XE3_CONFIG(PTL)`，没有 `FORCE_PROBE`。`iris_pci_ids.h` 里 PTL 的 `CHIPSET(...)` 也没有第五个 `FORCE_PROBE` 参数。25.1.6 / 25.2 才把 PTL 改成默认启用；我们锁的树比那新，不必设 `INTEL_FORCE_PROBE`。

`userland/BUILD.md` 的矩阵写了 Xe3 PTL `0xb080` 通过，并写明 noop shim 伪造的是 i915 uAPI。LNL、BMG、PTL 在真机上都要走 xe KMD。

### issue #11 和实机启动

[issue #11](https://github.com/watchthelight-labs/WTLIntelGfx/issues/11) 的机器是 Framework Laptop 13（Core Ultra X7 358H，Arc B390，`8086:b082`）。Linux 侧的 xe 日志就是上面的固件和 IP 版本来源。OpenCore 停在 `EXITBS:START`。维护者的判断和 Arrow Lake Legion 相同：MADT 里只有 x2APIC（type 9），XNU 只从 Local APIC（type 0）数 CPU，于是在控制台出现之前就停住。处理是用 [x2apic_to_lapic.py](https://github.com/watchthelight-labs/Legion-5-15IAX10-OpenCore/blob/main/scripts/x2apic_to_lapic.py) 改 APIC 表，在 OpenCore 里删掉原来的 `APIC` 再加转换后的表。这和驱动并行做。驱动编出来之前，这块机器进不了可以加载 kext 的系统。

公开材料里没有 PTL 核显在 macOS 物理机上点亮的记录。vibe 的桌面是 QEMU 里的 VF，扫描输出走 virtio-gpu。

## 5. 裸机相对 VF 多出来的事

vibe 的 README 写了：VM 显示是 VM 专有的；xe、LinuxKPI、sandbox 的修复不是。对照主线 xe 的 PF/VF 分叉，裸机 PF 还要自己做这些。VF 补丁覆盖不到的，标在后面。

| 事项 | VF 上 | 裸机 PF | 和点亮的关系 |
|---|---|---|---|
| 身份 | `has_sriov` + `test_is_vf()`，不加载固件，和 PF 上已经在跑的 GuC 握手 | 自己读 WOPCM，加载 GuC | 点亮的第一步 |
| GuC | 一份，在 PF 上 | GT0、GT1 各加载 `ptl_guc_70.bin` | 点亮 |
| HuC / GSC | VF 跳过 HuC 认证 | HuC 认证依赖 GSC 和 MEI proxy（实机 `mei_gsc_proxy`） | 不挡第一帧。6.14 的 `fork_xe.py` 也没加 GSC 105 |
| GGTT | PF 分一段给 VF | PF 自己管整段。ver ≥ 12.50 时 GSM 8MiB，对应 4GiB GGTT | probe 时预留 GOP 占用的那段，避免画到固件画面上 |
| stolen | 没有 | 有。实机 `Allocated fbdev into stolen` | 和 GGTT 预留一起做 |
| flat CCS | vibe 把 Xe2+ 压缩默认关掉，并写 VF CCS 要 7.2 的内核工作 | 6.14 在 GMD_ID 3000 上从 `graphics_xe2` 得到 `has_flat_ccs` | 第一帧压缩保持关闭（`ANV_XE2_COMPRESS` 不设）。CCS 的 BO 移动见下面 `0050` |
| 显示 | `probe_display = 0`，画面走 virtio-gpu（NMXVGAFB） | DMC、DC 状态、PSR、端口、DPLL | 第一帧用现有 XeGfxIntelFB 拷进固件帧缓冲。DMC/modeset 是下一阶段 |
| 中断 | memirq + MSI，没有 INTx | GT 和 display 的常规中断 + MSI | 用现有 MSI 路径。`0047` 的 memirq 分发不移植 |
| 电源 | 跳过 GuC PC、pcode、driver-FLR | SLPC / RC6、pcode、runtime PM | `0011` 要，否则 G2H 丢。完整 RC6 放在能稳定提交之后 |
| 早期 MMIO / CT 轮询 | `0007`、`0010`：VF 在 IRQ 安装前就和 PF 握手 | PF 的 GuC 加载在 IRQ 之后 | 不移植。若 probe 卡在 IRQ 安装前的 G2H，再把 `0010` 的轮询拿回来 |

## 6. 工作顺序

做到“面板上出现 GPU 合成的桌面”的依赖顺序如下。每一步都写了要动的补丁或文件。诊断补丁、`build-guest.sh`、virtio / QEMU 整段不在这条路径上，分类见 triage 文档。

### 里程碑 1：xe probe，两个 GT 的 GuC 加载成功

1. **构建。** `harness/score.py` 增加 xe 模块，源是 Linux 6.14 的 `drivers/gpu/drm/xe`，DRM / TTM / dma-buf 仍用 drm-kmod `c16de0f`。显示代码先编进来，用开关在运行时停住。i915 和 xe 分开链，避免两个 `drmn`。
2. **驱动名和探针。** 移植 vibe xkpi `0006`：`xe_pci_driver.name = "drmn"`。关掉 `ptl_desc.require_force_probe`。不移植 `0001`。
3. **固件表。** 在 `xe_uc_fw.c` 只加上 PTL 的 GuC（下限 70.54.0），M1 不定义 HuC 的 fw_def。kext Resources 只放入 `ptl_guc_70.bin`（70.72.1）。定义了 HuC 路径但文件缺失会让 `xe_huc_init` 返回 `-ENOENT` 导致 probe 失败，认证失败在 6.14 会走到 `xe_gt_assert`。GSC/HuC 认证留到后期（第 18 步）。
4. **runtime PM。** 确认 FreeBSD `linux_pm.c` 的 `pm_runtime_get_if_active` / `pm_runtime_get_if_in_use`。若返回 `-EINVAL`，按 vibe `0011` 改 `xe_pm.c`：运行态下 `pm_runtime_get_noresume()` 并返回成功。G2H worker 靠这个。
5. **非连续内核映射。** 用两段不相邻的页做和 stage 1 一样的 vmap 自测。失败则把 vibe `0012` 接到 `xg_vm.cpp`。`xe_lrc_init` 的 memcpy 会走到这里。
6. **不动面板。** xe display 初始化加一个默认开启的跳过开关，作用对齐 `i915_xegfx_no_display`。stolen 分配避开 stage 2 记下来的 GOP 画面（对齐 `xg_stolen_start`）。GGTT 初始化之前（`xe_ggtt_initial_clear` 把空洞清成 scratch 之前）按 `PLANE_SURF` 读出 GOP 帧缓冲的 GGTT 区间，插入一个 `drm_mm` 保留节点，同时覆盖 stolen 和 GGTT PTE 两部分。stage 4 之后读 pipe A 的帧计数，扫描停了就判失败；再核对 xe 加载前后 GOP 区间的 GGTT PTE 和像素校验值不变（帧计数发现不了 GGTT 被清成 scratch）。
7. **通过标准。** 两个 GT 都报告 GuC 在跑（实机是 70.72.1）。各引擎一次空提交能完成，中断经现有 MSI 路径进来。HuC 保持 `NOT_SUPPORTED`（不定义 fw_def），不做认证。

**必须回移的 B0 WA（M1 配 6.14，顺序按 bring-up 挂死概率）。** A0–B0 区间的 WA 不移植（RTP 区间左闭右开，不含 B0）。下面这些在 B0 上生效，6.14 缺失：

- `14025515070`（优先）：6.14 在 Xe3 上默认开 indirect ring state 且无缓解。M1 对 PTL 强制 `has_indirect_ring_state=0`（上游 v7.2 用 GuC ≥ 70.53 下发 ADS KLV `0x900e` 缓解，`f9a21696e37b`）。
- `16023105232`：所有引擎设 `RING_PSMI_CTL` 的 `RC_SEMA_IDLE_MSG_DISABLE`（bit 12），并回移 IDLEDLY 计算逻辑（`7c53ff050ba8`，v6.15）。
- `14023061436`：RCS/CCS 的 `TDL_CHICKEN`（0xe5f4）`QID_WAIT_FOR_THREAD_NOT_RUN_DISABLE`（bit 12）（`92029e0baa53`，v6.15）。
- `16028005424`：所有 GT 设 `GUC_INTR_CHICKEN`（0xc50c）的 `DISABLE_SIGNALING_ENGINES`（bit 1）（v7.0）。
- `13012615864`：`TDL_TSL_CHICKEN`（0xe4c4）`RES_CHK_SPR_DIS`（bit 6）（`2399bcc07c01`，v6.15）。
- `13011645652`：6.14 已有 ADS KLV `0x9008` 代码，只需把 OOB 规则扩到 3000（`6fc957185e16`，v6.17 覆盖 30.00）。
- `16026007364`：media 30.00 的 KLV `0x900c`（`d72779c29d82`，v6.18；M2–M4 不用 media，但 GT1 仍进出 RC6）。
- `14025883347`：GuC-only reset 时 GuC DMA 失败（`c57db41b8d2c`，v7.1）。kext 卸载重载时 GuC 仍在跑，`xe_uc_sanitize_reset` 会触发，开发循环里会遇到。
- `14022293748`：KLV `0x9009`（`32af900f2c6b`，v6.15；6.14 规则只覆盖 LNL，扩展规则即可）。

### 上实机后首先验证

issue #11 的机器能进系统后，先做这三项再往下走：

1. `B080` 实际的 GMD_ID 和 stepping（GMD_ID 寄存器 0x132000 / 0x380000），确认是否和 `B082` 一样落在 30.00。
2. GuC 70.72.1 在 6.14 的 ADS/CT 代码上是否可用（6.14 是 LNL 时期的代码，上游 PTL 最低是 v6.17 的 70.47.0；M1 开 GuC log 并核对 ADS 大小）。
3. Mesa 26.x ANV 的 xe backend 与 6.14 xe uAPI 的兼容性（M2 前先在 Linux 6.14 上跑一次 ANV xe 后端冒烟测试做对照）。


### 里程碑 2：接到现有 ANV 和 Metal 插件

8. **mmap。** 把 vibe mesa `0001` 的行为补到 `userland/patches/mesa-xegfx.patch` 的 xe backend：Darwin 上 ANV 用 `NMX_DRM_IOCTL_MMAP`，不走设备节点的 mmap(2)。内核侧扩展 `xg_i915_map.c` 的查找，让 xe BO 的 offset 也能映射。写这段时核对页对齐用 `(PAGE_SIZE - 1)`。vibe `0024` 是因为他们的 `nmx_mmap` 用了 LinuxKPI 的 `PAGE_MASK`（`~0xfff`），FreeBSD 的 `PAGE_MASK` 是低 12 位，两套宏咬合会拒绝每一个对齐的 offset。
9. **压缩默认关。** mesa `0004` 里 `.compressed = ver >= 20 && getenv("ANV_XE2_COMPRESS")` 这一行要有。cached coherent PAT 已经在 `mesa-xegfx.patch`。不设 `ANV_XE2_COMPRESS`。
10. **缓存。** 移植 vibe `0033`、`0034` 的行为到我们的 highmem / `clear_page`：内核映射是 write-back 的，TTM 经它清 WC 页时，脏行稍后会盖住 GPU 的写入。落点是 `xkpi` 对 LinuxKPI 页操作的覆盖，不是换掉整份 FreeBSD `linux_page.c` 以外的无关改动。
11. **通过标准。** 现有 Metal 插件在 PTL 上创建一个设备，compute 和一次离屏 draw 读回正确。插件和 `XeGfxAccel` 不换。

### 里程碑 3：Xe3 的渲染 workaround

12. **三条 LRC workaround，** 直接移植 vibe `0048`：`14026781792`（`FF_MODE` `DIS_TE_PATCH_CTRL`）、`22021007897`（`SBE_PUSH_CONSTANT_BEHIND_FIX_ENABLE`）、`14024681466`（`FAST_CLEAR_VALIGN_FIX`）。6.14 的 `xe_wa.c` 没有这三条，它们在 context image 里，PF 和 VF 都要写。版本范围是 graphics 30.00–30.05（第一条到 35.10），B0 也包含。主线里另有一批 A0–B0 的 WA，范围不含 B0；B082 是 B0，那些先不移植。
13. **G2H fence。** 在 6.14 的 `xe_guc_ct.c` 里，`guc_ct_send_recv` 用 `READ_ONCE` 读 `g2h_fence.done`，`parse_g2h_response` 用 `WRITE_ONCE` 写。vibe `0049` 的补丁锚点假定已经打过 `0010`（等待被拆成两处）。点亮不带 `0010`，按原文件的等待点改，不按那份 diff 硬套。
14. **`0050` 先不打。** 它删掉 `xe_rpm_reclaim_safe` 里的 `&& !xe->info.has_sriov`。6.14 的裸机路径不设置 `has_sriov`，这个条件为真，system CCS 的 BO 移动不会走那条 `drm_WARN`。哪天 `ptl_desc.has_sriov` 打开（主线就是这样，而且 PF 仍是 PF），再把 `0050` 一起带上。

### 里程碑 4：面板和桌面

15. **第一帧。** `XeGfxAccel` 把 Metal 合成结果送进固件帧缓冲，`XeGfxIntelFB` / AGDC 维持现有的面板登记。这是 Arrow Lake 已经走通的路径。vibe 的 nvidia-macos-driver `0001`–`0011`、`0008` 之后的 virtio-gpu、以及全部 QEMU 补丁不移植。
16. **合成正确性。** 若 WindowServer 的管线仍全量写 binding，移植 nvidia `0043`（布局外的 `[[color(n)]]` 跳过，而不是清掉整个 mask）。descriptor set 复用（`0026`）和 GL 的 primitive-restart（`0027`）放在桌面已经出现之后。
17. **xe 自己的显示。** 在拷贝路径稳定之后再打开：加载 `xe3lpd_dmc.bin`，DC 状态，PSR，端口和 DPLL，显示中断。实机日志里的 selective-fetch 失败留到这时看。全 GGTT 的管理在打开 display 之前核对，避免和 GOP 的 stolen 分配重叠。
18. **GSC。** `ptl_gsc_1.bin` 加进固件表，并有一个 MEI proxy 能完成 HuC 认证。6.14 的 GSC 代码只认识 102/104，这一步要么回移 105 的加载，要么换更新的 xe。它不在第一帧的依赖里。

### 点亮之后再做

- vibe `0046`：`linux_alloc_pages` 对 `__GFP_NORETRY` 已经加上 `VM_ALLOC_NORECLAIM`，但 order > 0 仍调用 `vm_page_alloc_noobj_contig`。碎片化后这次连续分配会走很久。TTM 建大 BO 变慢时，order > 0 直接返回 NULL。
- vibe `0036`/`0037`：userptr 写接线失败时退回只读。i915 路径上只读区间会在提交时失败，xe 也会碰到。
- vibe `0045`：用户页接线在任务退出后仍可能碰到已经销毁的 `vm_map`。`0043`/`0044` 修的是 NullMoth 按 `proc_t` / `thread_t` 指针长期缓存、且不释放的记录；本仓库的 `pfind` / `tdfind` 按 pid 和 tid 查，不移植那两份。
- drm-kmod `0001`：`drm_file_update_pid` 里对 FreeBSD 的整数 pid 跳过 `synchronize_rcu()`。每个新 ioctl 线程少等一次宽限期。
- libdrm `0004`/`0005` 和 nvidia `0045`、xkpi `0032`：App Sandbox 完全打不开 `/dev/dri` 时的 token fd。WindowServer 的 IOKit 回退已经有了，这是给计算器、WebKit GPU 进程的。
- issue #11 的 OpenCore x2APIC 表。没有它，Framework 上无法做任何阶段的实机验证。

## 7. 前 10 项

| # | 工作 | 依赖 | 结束时能看到什么 |
|---|---|---|---|
| 1 | harness 编 Linux 6.14 xe，直接编上游 `xe_pt_walk`；i915/xe 的 `drmn` 分开链 | drm-kmod `c16de0f` | kext 链上，尚未 probe |
| 2 | `0006` 驱动名 `drmn`；关掉 `require_force_probe`；不加 `has_sriov` | 1 | 设备能 attach |
| 3 | `xe_uc_fw.c` 只加 PTL GuC 条目（下限 70.54.0，不定义 HuC），Resources 里只放 70.72.1 | 2 | 固件请求打到 kext 资源 |
| 4 | `0011` runtime PM，G2H 不再被 `-EINVAL` 丢掉 | 3 | GuC 通信能完成 |
| 5 | 非连续 vmap 自测，失败则移植 `0012` | 4 | `xe_lrc_init` 不再 fault |
| 6 | 显示保持 GOP；stolen 预留 + GGTT 初始化前预留 GOP 区间（含 PTE/像素校验）；GT0 和 GT1 的 GuC 都在跑 | 5 | 里程碑 1。面板仍是固件画面 |
| 7 | ANV xe backend 的 mmap（mesa `0001`）接到现有 `'N'` ioctl | 6 | Vulkan 设备能映射 BO |
| 8 | `0048` 三条 LRC WA，`0049` G2H `READ_ONCE`/`WRITE_ONCE` | 7 | 渲染读回正确 |
| 9 | `0033`/`0034` 非 WB 页刷出缓存；Xe2+ 压缩默认关 | 7 | 合成缓冲不被脏 cache line 盖住 |
| 10 | 现有 XeGfxAccel + XeGfxIntelFB 把帧送进固件帧缓冲 | 8、9 | 面板上出现 GPU 合成的桌面 |

第 10 项不包含 DMC、PSR、GSC、virtio。那些在里程碑 4 的后半和第 18 步。

## 8. 风险

- **GMD_ID 表够用，不是主要风险。** 6.14 有 graphics/media 3000/3001，B082 实测 30.00 正好落在里面。主线多出来的 30.03 是 WCL，30.04/30.05 是 xe3p 系列，都不是 PTL。B080 按 SKU 推断也是 30.00，等实机读一次 GMD_ID 确认。基线要上调的理由是 WA 缺失和固件处理，不是这张表：M1 留在 6.14 并配上第 6 节的 B0 WA 回移清单，中期把 xe 对齐到 v7.2（drm-kmod、DRM core、TTM 跟着升级的成本另算）。换 7.x 的 xe 要先补 drm-kmod 没有的 DRM / TTM 符号，vibe 的 README 把这件事排除在当时的范围之外。点亮不走那条。
- **6.14 没有 PTL 的 GSC 105。** M1 不定义 HuC fw_def（状态 `NOT_SUPPORTED`），第一帧不做 HuC 认证。媒体和 PXP 要等固件表和 MEI proxy，或者换更新的 xe。
- **display 关闭时 GGTT 初始化会清掉 GOP 映射。** `xe_ggtt_initial_clear` 把 GGTT 所有空洞写成 scratch，GOP 帧缓冲的 GGTT 映射会被抹掉，面板变黑或花屏，aperture 写入也会落到 scratch。pipe 帧计数照样增加，发现不了这个问题。第 6 步在 GGTT 初始化前预留 GOP 区间，并用 PTE 和像素校验值验收。
- **display probe 会拆 GOP。** i915 在 Legion 上已经发生过。xe 的第一阶段必须把显示停在“不改扫描”的状态，并用 pipe 帧计数检查（帧计数只管扫描，不管上面的 GGTT 映射）。
- **`withAddressRanges` 可能只映射第一段。** 不先做不相邻页的自测，第一次 `xe_lrc_init` 就是 kernel panic。
- **两个 `drmn`。** 和 i915 编进同一个 kext 且都改名为 `drmn` 时，Arrow Lake 的绑定会被换掉。
- **没有裸机对照。** VF 上的桌面不证明 WOPCM、双 GuC、stolen、显示中断。Framework 的机器还停在 OpenCore `EXITBS`（issue #11），驱动阶段无法在这块 PTL 上验证，直到 APIC 表换过。
- **Mesa 矩阵不覆盖 xe uAPI。** `0xb080` 在 noop shim 上通过，只说明 26.3 认识这颗芯片。xe backend 的 mmap 是里程碑 2 的实工作。
- **基线会消失。** NullMoth HEAD 已经删了 `gpu-port/`。后续对照锁 `d96eaca` 和 vibe `7246d38`。

## 9. 补丁数量

115 个 patch 的分类在 [nullmoth-patch-triage.md](nullmoth-patch-triage.md)。汇总：

| 分类 | 数量 |
|---|---|
| 裸机需要 | 32 |
| 忽略（诊断、构建脚本、virtio/QEMU、本仓库已有、6.14 点亮用不上的 walker/RCU/临界区/指针缓存） | 78 |
| VF 专用 | 5 |
| 合计 | 115 |

32 项里，点亮路径实际要落地的是第 7 节那 10 步所点名的补丁。其余裸机项（sandbox token、高阶页、userptr 只读、task 引用、GL、descriptor 复用）排在第一帧之后。
