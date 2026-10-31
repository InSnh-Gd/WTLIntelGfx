# NullMoth / vibe-nullmoth 补丁分类

对照的补丁树是 [ericek111/vibe-nullmoth-xe3-qemu](https://github.com/ericek111/vibe-nullmoth-xe3-qemu) `7246d38`。xkpi 与 nvidia-macos-driver 系列打在 [nullmoth/nvidia-macos-driver](https://github.com/nullmoth/nvidia-macos-driver) `d96eaca` 的 `gpu-port/` 上。

[VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics](https://github.com/VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics) 的 `NullMoth-Xe/` 与 vibe 仓库这 115 个 patch 逐字节相同，不另作一套。

分类：

- **裸机需要**：物理机 Panther Lake 的路径要用到的行为。点亮顺序见 [panther-lake-xe-port-plan.md](panther-lake-xe-port-plan.md)。
- **VF专用**：只服务 SR-IOV VF（`has_sriov`、VF 早期 MMIO、IRQ 前的 CT 轮询、VF 复位、memirq）。
- **忽略**：临时诊断、客户机构建脚本、virtio-gpu / QEMU，以及本仓库已经有的行为。

合计 115。裸机需要 34，忽略 76，VF专用 5。

难度「不移植」表示这一项不进点亮分支。裸机需要里标了「第一帧之后」的，同样先不挡 GuC 和第一帧。

## xkpi（50）

打在 `d96eaca:gpu-port/xkpi`。

| 文件 | 作用 | 分类 | 依赖 | 难度 | 本仓库落点 |
|---|---|---|---|---|---|
| `0001-xe-enable-the-SR-IOV-VF-path-on-Panther-Lake-.has_sr.patch` | 给 6.14 的 ptl_desc 设 has_sriov，VF 才进入 VF 模式并跳过本地加载固件 | VF专用 | 无 | 不移植 | 不改 ptl_desc.has_sriov |
| `0002-build-guest.sh-build-NMXGPU-inside-the-macOS-VM.patch` | 在 macOS VM 里调用 NullMoth 的 all.sh / kext 构建 | 忽略 | 无 | 不移植 | build/build_xegfx.sh 已是本仓库的构建 |
| `0003-build-guest.sh-create-fbroot-FreeBSD-root-include-vi.patch` | 为客户机构建准备 FreeBSD 头文件符号链接 | 忽略 | 0002 | 不移植 | harness/score.py 的头文件路径 |
| `0004-build-guest.sh-resolve-uapi-drm-xe_drm.h-for-xe.patch` | 让 uapi/drm/xe_drm.h 在客户机构建的 -I 下能被找到 | 忽略 | 0003 | 不移植 | 编 xe 时把头文件路径设对即可，不搬这个脚本 |
| `0005-build-guest.sh-keep-NMXNPU-s-kext-stub-out-of-the-NM.patch` | 链接前删掉 NPU kext 的目标文件，避免 kmod_info 进 GPU kext | 忽略 | 0002 | 不移植 | 本仓库不编 NMXNPU |
| `0006-xe-name-the-PCI-driver-drmn-so-LinuxKPI-registers-it.patch` | xe 的 pci_driver 名字改成 drmn，LinuxKPI 才会把它挂到 vgapci | 裸机需要 | 无 | 低 | 编译的 xe_pci.c；shim/src/fbsd/xg_pci.c 已创建 drmn 子设备 |
| `0007-xe-VF-set-up-the-root-GT-s-MMIO-before-the-early-GuC.patch` | VF 在早期 GuC GMD_ID 查询前初始化 root GT 的 MMIO，否则基址是 NULL | VF专用 | 0006 | 不移植 | PF 直接读 GMD_ID 寄存器，不走 xe_gt_sriov_vf_bootstrap |
| `0008-xe-VF-temporary-CT-IRQ-diagnostics-on-G2H-timeout.patch` | G2H 超时和 VF memirq 的临时打印 | 忽略 | 0007 | 不移植 | 无 |
| `0009-fix-diag-macro-use-build-guest-refuses-to-link-after.patch` | 修 0008 诊断宏的括号，并让构建在有失败日志时不链接 | 忽略 | 0008 | 不移植 | harness 已在编译失败时停住 |
| `0010-xe-VF-poll-CT-replies-while-IRQs-are-not-installed-y.patch` | IRQ 尚未安装时轮询 VF 的 CT 回复。6.14 的 VF 握手在 xe_irq_install 之前 | VF专用 | 0007 | 不移植 | PF 的 GuC 加载在中断安装之后。若 probe 卡在那之前再拿回来 |
| `0011-xe-runtime-PM-get_if_active-in_use-always-succeed-Li.patch` | pm_runtime_get_if_active / in_use 从 -EINVAL 桩改成成功，否则 G2H worker 丢掉每条 GuC 回复 | 裸机需要 | 无 | 低 | 先看 FreeBSD linux_pm.c；仍是桩则改编译进来的 xe_pm.c |
| `0012-xnu-map-page-arrays-through-one-descriptor-per-physi.patch` | 多段物理页按段各做一个 IOMemoryDescriptor，再 IOMultiMemoryDescriptor 合并。一次 withAddressRanges 只映射第一段 | 裸机需要 | 无 | 中 | shim/src/xnu/xg_vm.cpp 的 xg_vm_map_ranges；先做不相邻页自测 |
| `0013-cdev-give-each-open-a-vnode-iminor-and-accept-d_fdop.patch` | 每次 open 带 vnode，iminor 才能得到 DRM minor；d_fdopen 在 finit 之后返回 ENXIO 视为成功 | 忽略 | 无 | 不移植 | shim/src/fbsd/xg_fd.c。i915 的 /dev/dri 已经能被 ANV 打开 |
| `0014-devfs-release-clone-minors-devfs-frees-without-an-op.patch` | stat 产生的 clone minor 在未 open 时释放，避免 minor 表耗尽 | 忽略 | 无 | 不移植 | 现有 devfs clone 已支撑数小时桌面。若 xe 的 stat 风暴把 minor 打满再看 |
| `0015-bus-a-driver-instance-on-a-PCI-function-is-a-PCI-dev.patch` | DRM 子设备也算 PCI 设备，DRM_IOCTL_GET_PCIINFO 才有 vendor/device | 忽略 | 无 | 不移植 | xkpi/src/i915/xg_drm_sync.c 已回答 GET_PCIINFO |
| `0016-xe-pt-walk-callbacks-get-a-child-copy-post_descend-o.patch` | 修 NullMoth 自写 walker：回调拿到 child 的副本，pt_post_descend 只在真正下降之后调用 | 忽略 | 无 | 不移植 | 直接编 Linux 6.14 的 xe_pt_walk.c，不编 override/xe/nmx_xe_pt_walk.c |
| `0017-kext-one-shot-opt-in-through-NVRAM-nullmoth-gpu-once.patch` | NVRAM 一次性开关，下一次启动不再加载 GPU kext | 忽略 | 无 | 不移植 | 本 kext 本来就不在启动时加载 |
| `0018-TEMP-nmx_mmap-diagnostics.patch` | nmx_mmap 失败路径的临时 printf | 忽略 | 无 | 不移植 | 无 |
| `0019-devfs-detect-and-repair-entry-points-that-return-wit.patch` | 系统调用返回用户态时若中断仍关着就 sti。原因是他们的 per-CPU 临界区 | 忽略 | 0020 | 不移植 | shim 的 spinlock_enter 按线程嵌套，最外层才恢复中断 |
| `0020-spin-mutexes-nest-in-the-per-CPU-critical-count-per-.patch` | 自旋锁不再各自保存中断标志，改走临界区计数，避免乱序解锁把中断打开 | 忽略 | 无 | 不移植 | shim/src/fbsd/xg_lock.c 的 __mtx_lock_spin_flags 已用 spinlock_enter |
| `0021-TEMP-record-the-outermost-critical-section-opener-fo.patch` | 记录最外层临界区的返回地址，供 0019 的日志使用 | 忽略 | 0019 | 不移植 | 无 |
| `0022-build-guest-counts-runtime-failures-fix-noinline-spe.patch` | 客户机构建统计编译失败；noinline 宏和属性拼写冲突 | 忽略 | 0021 | 不移植 | 无 |
| `0023-critical-sections-per-thread-nesting-per-CPU-counts-.patch` | 临界区从 per-CPU 改成 per-thread。线程在临界区内阻塞后换 CPU，旧计数会把中断留在关闭状态 | 忽略 | 0020 | 不移植 | xg_kern.c 的 critical_enter_KBI 已经计在 td_critnest 上 |
| `0024-nmx_mmap-page-alignment-checks-used-LinuxKPI-s-PAGE_.patch` | 对齐检查改用 (PAGE_SIZE-1)。LinuxKPI 的 PAGE_MASK 是 ~0xfff，会拒绝所有已对齐的 offset | 裸机需要 | 无 | 低 | 扩展 xg_i915_map.c / xe mmap 时用 (PAGE_SIZE-1)。FreeBSD 侧现有代码的 PAGE_MASK 是低 12 位 |
| `0025-cdev-wait-ioctls-report-a-timeout-as-macOS-ETIME-101.patch` | 等待类 ioctl 的 ETIMEDOUT(60) 改成 Darwin ETIME(101)，Mesa 才能得到 VK_TIMEOUT | 忽略 | 无 | 不移植 | shim/src/xnu/xg_fd.cpp 的 xg_fd_ioctl_errno 已做这个转换 |
| `0026-pci-ask-IOPCIFamily-for-an-MSI-vector-a-VF-has-no-le.patch` | 向 IOPCIFamily 要 MSI。VF 没有 INTx，不调用 configureInterrupts 就没有消息中断 | 忽略 | 无 | 不移植 | docs/xg_pci.md：pci_alloc_msi 向量不够时已经 configureInterrupts。PF 还有 INTx |
| `0027-debug.nmxgpu_dump-on-demand-xe-state-dump-build-stam.patch` | 按需 dump xe 状态的 sysctl 和构建戳 | 忽略 | 无 | 不移植 | 已有 debug.xegfx_log / xegfx_results |
| `0028-diag-log-the-dump-sysctl-registration.patch` | 打印 dump sysctl 是否注册成功 | 忽略 | 0027 | 不移植 | 无 |
| `0029-state-dump-through-NMX_DRM_IOCTL_DEBUG_DUMP-instead-.patch` | 状态 dump 从 sysctl 改成 DRM ioctl | 忽略 | 0027 | 不移植 | 无 |
| `0030-state-dump-own-drm_printer-LinuxKPI-printk-has-no-pV.patch` | 自备 drm_printer，因为 LinuxKPI 的 printk 没有 %pV | 忽略 | 0029 | 不移植 | 无 |
| `0031-kext-forward-a-power-on-as-resume-only-after-a-suspe.patch` | IOKit 初始 power-on 不再转成 device_resume，避免 GuC submission 计数变成 -1、用户队列全部暂停 | 忽略 | 无 | 不移植 | xg_kext.cpp 没有 registerPowerDriver。以后接 IOKit 电源再按此处理 |
| `0032-DRM-over-IOKit-IOAccelNMXDRMClient-for-sandboxed-pro.patch` | 用 IOKit user client 承载 DRM ioctl，给不能对设备文件做 ioctl 的进程 | 裸机需要 | 无 | 中 | WindowServer 路径已有。App Sandbox 完全打不开 /dev/dri 的 token 还没有，放在第一帧之后 |
| `0033-highmem-kunmap-writes-a-non-write-back-page-s-lines-.patch` | kunmap 时把非 write-back 页的脏 cache line 写出去。内核视角始终是 WB，会盖住 GPU 写入 | 裸机需要 | 无 | 中 | xkpi 对 LinuxKPI highmem/kunmap 的覆盖 |
| `0034-clear_page-writes-a-non-write-back-page-s-lines-out-.patch` | clear_page 对非 WB 页同样把脏行写回。TTM 清 WC 池页时否则读回大片 0 | 裸机需要 | 0033 | 中 | 与 0033 同一处页操作覆盖 |
| `0035-diag-log-userptr-pin-and-bind-ops-copy-failures-temp.patch` | userptr pin 和 bind 失败的临时日志 | 忽略 | 无 | 不移植 | 无 |
| `0036-user-wire-fall-back-to-a-read-only-wiring-when-the-r.patch` | 用户页写接线失败时改用只读接线。只读区间（常量、映射文件）否则无法提交 | 裸机需要 | 无 | 中 | shim 的 user wire。第一帧之后，和 i915 上的 userptr 只读问题同类 |
| `0037-user-wire-read-only-fallback-only-in-nmx_xnu_user_wi.patch` | 把 0036 的只读退路限制在 nmx_xnu_user_wire，上一提交误改了另一个函数 | 裸机需要 | 0036 | 低 | 和 0036 一起落到 user wire |
| `0038-fork_xe.py-VF-shutdown-without-PF-only-resets-backpo.patch` | VF 关机不碰 PF 专有的 FLR 寄存器，改走 VF2GUC_VF_RESET，避免每次重启等 3 秒超时 | VF专用 | 0001 | 不移植 | PF 走自己的复位 |
| `0039-bsdcompat-per-thread-RCU-record-slots-and-a-thread-e.patch` | 为每线程准备 RCU 记录槽，线程退出时结束仍打开的读端 | 忽略 | 无 | 不移植 | sched_pin 已把线程绑在 CPU 上（shim/include/sys/sched.h） |
| `0040-linux_rcu-fork-end-each-RCU-read-section-on-the-reco.patch` | rcu_read_unlock 结束的是开始时那条记录。读者迁移后会拆错 per-CPU epoch | 忽略 | 0039 | 不移植 | 同上。宽限期开销见 drm-kmod 0001 |
| `0041-linux_rcu-fork-report-migrated-readers-per-RCU-type.patch` | 按 RCU 类型统计发生过迁移的读者 | 忽略 | 0040 | 不移植 | 无 |
| `0042-nmx-cdev-log-a-user-mmap-only-when-it-fails.patch` | 用户 mmap 只在失败时打印 | 忽略 | 无 | 不移植 | 无 |
| `0043-bsdcompat-a-process-record-whose-pid-changed-belongs.patch` | pid 已变的进程记录视为已退出进程的残留。XNU 会复用 pid | 裸机需要 | 无 | 中 | shim 的进程/线程记录。WindowServer 重启后再核对，不挡第一帧 |
| `0044-bsdcompat-a-thread-record-whose-xnu-thread-id-change.patch` | XNU thread id 已变的线程记录视为已退出线程。否则新线程继承死进程的 mm | 裸机需要 | 0043 | 中 | 同上 |
| `0045-nmx_mm-hold-a-task-reference-for-each-mm-record-and-.patch` | mm 记录和每段 wiring 持有 task 引用，任务退出后映射为空并返回 EFAULT，而不是用悬空 task | 裸机需要 | 0044 | 中 | shim 的 user wire / vm。与 0043 一起核对 |
| `0046-linux_page-refuse-opportunistic-higher-order-page-al.patch` | order>0 且 __GFP_NORETRY 的分配直接失败，TTM 立刻用单页。碎片化后 8MB BO 从约 740ms 降到 1ms 以内 | 裸机需要 | 无 | 低 | xkpi/src/lkpi/linux_page.c。BO 分配变慢时再做 |
| `0047-xe-fork-always-dispatch-VF-memirq-user-and-GUC2HOST-.patch` | VF memirq 每次都分发 user 和 GUC2HOST，按 Intel 对内存中断的编程说明从 7.2 回移 | VF专用 | 0001 | 不移植 | PF 用 GT/display 中断加 MSI，不走 memirq |
| `0048-xe-fork-Xe3-LRC-workarounds-14026781792-22021007897-.patch` | 三条 Xe3 LRC workaround：14026781792、22021007897、14024681466，写在 context image 里 | 裸机需要 | 里程碑1 | 低 | 直接改编译的 xe_wa.c 和 xe_gt_regs.h |
| `0049-xe-fork-READ_ONCE-WRITE_ONCE-on-the-G2H-fence-done-f.patch` | G2H fence 的 done 标志：等待侧 READ_ONCE，完成侧 WRITE_ONCE | 裸机需要 | 0011 | 低 | 直接改编译的 xe_guc_ct.c |
| `0050-xe-fork-runtime-resume-from-reclaim-is-safe-on-a-VF-.patch` | xe_rpm_reclaim_safe 去掉 !has_sriov。6.14 在 has_sriov 时把 system CCS 的 BO 移动打进 drm_WARN | 忽略 | 0001 | 不移植 | 点亮路径不设 has_sriov。以后打开该标志时再打这一处 |

## nvidia-macos-driver（47）

打在 `d96eaca` 的驱动树（NMXVGAFB、NMXAGDC、NMXAccel、plugin、translator）。

| 文件 | 作用 | 分类 | 依赖 | 难度 | 本仓库落点 |
|---|---|---|---|---|---|
| `0001-VM-display-for-the-Intel-VF-NMXVGAFB-head-0-NMXAccel.patch` | 给 QEMU VGA 加 NMXVGAFB，作为 head 0，并让插件在 VF 上接纳 WindowServer | 忽略 | 0001 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0002-VM-display-NMXAGDC-AGDC-for-the-VF-NMXVGAFB-NMXVGAFB.patch` | 为 VF 生成 NMXAGDC，并把 NMXVGAFB 放进 IOFramebuffer 匹配类，避免 IONDRV 再加一个无 pipe 的头 | 忽略 | 0001 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0003-NMXVGAFB-Intel-named-class-for-CoreDisplay-s-IOPrese.patch` | 类名含 Intel，满足 CoreDisplay 的 IOPresentment 厂商检查，并报扫描地址 | 忽略 | 0001 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0004-NMXAccel-fake-GPU-VAs-for-the-VM-display-deliver-fra.patch` | 给显示家族假的 GPU 虚拟地址，并在 VM head 就绪时送 framebuffer_did_power_on | 忽略 | 0001 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0005-VM-display-frames-reach-the-screen-NMXVGAFB-grants-s.patch` | nvAllocVram 用连续系统内存，并以 60Hz 重拷前缓冲 | 忽略 | 0001 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0006-VM-display-front-buffer-recopy-only-for-a-second-aft.patch` | 前缓冲重拷只持续事务之后的一秒 | 忽略 | 0005 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0007-VM-display-arms-itself-no-sysctls-no-WindowServer-re.patch` | 占住 registry 直到 head 武装完成，显示管在 NMXVGAFB::open 里建好 | 忽略 | 0002 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0008-NMXVGAFB-virtio-gpu-blob-scan-out-virtio-vga-blob-tr.patch` | 小型 virtio-gpu 1.x 传输，扫描从 VGA BAR 换到 guest blob | 忽略 | 0001 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0009-NMXAGDC-use-the-framebuffer-and-GPU-NMXAccel-hands-t.patch` | NMXAGDC 使用 NMXAccel 交过来的 PCI 设备和 framebuffer | 忽略 | 0002 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0010-NMXVGAFB-scan-presented-surfaces-out-of-their-own-pa.patch` | 被呈现的 IOSurface 自己的页做成 virtio-gpu blob 再扫描 | 忽略 | 0008 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0011-NMXAccel-zero-copy-VM-display-present-by-switching-t.patch` | virtio 扫描时 performTransaction 切到该 surface，停止前缓冲重拷 | 忽略 | 0010 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0012-NMXAGDC-report-plane-0-s-colour-stages-CSC-lineariza.patch` | AGDC 0x711 回答 plane 0 的 CSC、gamma、linearization，CoreDisplay 不再每帧做软件色彩 | 忽略 | 无 | 不移植 | 现有 XeGfxAGDC / 插件路径已经在 Arrow Lake 上合成桌面 |
| `0013-NMXVGAFB-flush-a-presented-surface-only-for-1-s-afte.patch` | 空闲的 virtio 扫描不再被 VBL 永远刷新 | 忽略 | 0008 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0014-NMXVGAFB-debug.nmxfb_vtiming-present-gaps-scan-out-s.patch` | debug.nmxfb_vtiming：呈现间隔和 virtio 命令耗时 | 忽略 | 0008 | 不移植 | 无 |
| `0015-NMXAccel-ordered-VM-display-flips-the-flip-waits-for.patch` | 翻转放到 thread call 上，等像素写完再 signalTransactionInterrupt | 裸机需要 | 桌面已出现 | 中 | kexts/XeGfxAccel 的送帧顺序。第一帧沿用现有拷贝，卡顿再移植 |
| `0016-plugin-WindowServer-s-commitAndWaitUntilSubmitted-wa.patch` | 有序翻转打开时，commitAndWaitUntilSubmitted 在排队时返回，不等 GPU | 裸机需要 | 0015 | 低 | plugin/。与 0015 一起 |
| `0017-NMXVGAFB-the-VM-display-runs-at-120-Hz-boot-arg-nmxv.patch` | VM 模式和 VBL 按 120Hz，可用 nmxvgafb_hz 覆盖 | 忽略 | 0001 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0018-NMXVGAFB-NMX_SCANOUT_FINAL-no-VBL-re-flush-of-a-surf.patch` | 像素已最终的翻转只刷一次，后续 VBL 不再改写 | 忽略 | 0015 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0019-NMXAccel-order-VM-display-flips-on-NMXPublished-NMXP.patch` | 用 IOSurface 的 NMXPublished 与 NMXPending 比较来决定翻转，不用 lock seed | 裸机需要 | 0015 | 中 | XeGfxAccel 与 plugin 的现有 pending 标记。协议不同，桌面卡顿时再对齐 |
| `0020-plugin-NMXPending-NMXPublished-surface-values-for-or.patch` | 插件在提交时写 NMXPending，拷出完成后写 NMXPublished | 裸机需要 | 0019 | 低 | plugin/ |
| `0021-NMXAccel-create-gNVSVPendLock-with-compare-and-swap.patch` | 表面 pending 锁用 compare-and-swap 创建，避免两个首次调用者各分配一把 | 裸机需要 | 无 | 低 | kexts/XeGfxAccel 里对应的锁初始化 |
| `0022-NMXVGAFB-release-the-display-hold-when-the-accelerat.patch` | 加速器先武装完 head 时立刻放下 registry hold，不等 20 秒 | 忽略 | 0007 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0023-NMXVGAFB-debug.nmxfb_shot-the-scan-out-s-pixels-as-t.patch` | debug.nmxfb_shot 把 virtio 扫描上的像素倒出来 | 忽略 | 0008 | 不移植 | 无 |
| `0024-plugin-a-buffer-texture-aliases-its-buffer-when-the-.patch` | buffer texture 在线性图像接受该内存类型时直接别名到 buffer | 忽略 | 无 | 不移植 | plugin/ 已有同类处理（I-120 一类的 buffer texture） |
| `0025-plugin-IOSurface-textures-on-an-integrated-GPU-are-i.patch` | 核显上 IOSurface 纹理是表面自身页上的线性图像，不再拷入拷出 | 忽略 | 0024 | 不移植 | plugin/ 对 8086 已走 host-pointer / 表面页 |
| `0026-plugin-reuse-retired-descriptor-sets-instead-of-free.patch` | 回收退役的 descriptor set。ANV 每次分配会清掉全部 binding | 裸机需要 | 桌面已出现 | 中 | plugin/。第一帧之后的 CPU 占用 |
| `0027-plugin-Apple-s-GL-renderer-draws-without-a-compute-p.patch` | 实现 primitive-restart 和 last-provoking-vertex，GL 渲染器不再每画一次用 compute 改写 index | 裸机需要 | 桌面已出现 | 中 | plugin/。OpenGL 路径，不挡 WindowServer 的 Metal 合成 |
| `0028-plugin-tracing-costs-nothing-while-it-is-off.patch` | nvtrace 收成宏，关闭时不读时钟、不求值参数 | 忽略 | 无 | 不移植 | plugin/ 现有跟踪开关 |
| `0029-plugin-diagnostics-per-API-call-census-build-stamp-t.patch` | 每个入口的调用计数、构建戳、第一条函数常量的日志 | 忽略 | 无 | 不移植 | 无 |
| `0030-plugin-save-a-failing-translator-input-while-tmp-nvm.patch` | 存在标记文件时，把翻译器拒绝的 LLVM IR 写出来 | 忽略 | 无 | 不移植 | 无 |
| `0031-translator-split-vector-loads-over-GEP-indexed-slots.patch` | 把跨类型 GEP 的向量加载拆成按 lane 的 bitcast。Apple GL 的 ivec3 uniform 走这条 | 忽略 | 无 | 不移植 | translator/ 已有对应拆分 |
| `0032-translator-specialize-internal-callees-for-constant-.patch` | 采样器选择是常量时克隆内部被调用者，折叠 sampler phi | 忽略 | 无 | 不移植 | translator/ 已有对应特化 |
| `0033-NMXVGAFB-virtio-gpu-completions-by-MSI-X-and-a-fence.patch` | virtio-gpu 命令用 MSI-X 完成，并发送可在锁存点应答的 fenced RESOURCE_FLUSH | 忽略 | 0008 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0034-NMXVGAFB-flips-complete-at-the-host-s-latch-point-VB.patch` | 最终翻转在主机锁存该帧时返回，VBL 线程跑在这个网格上 | 忽略 | 0033 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0035-NMXAccel-ordtrace-stage-times-in-microseconds.patch` | 有序翻转各阶段的微秒级计时 | 忽略 | 0019 | 不移植 | 无 |
| `0036-NMXVGAFB-hardware-cursor-over-virtio-gpu-s-cursor-qu.patch` | 指针走 virtio-gpu 的 cursor 队列 | 忽略 | 0008 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0037-NMXVGAFB-debug.nmxfb_vtrace-slot-index-without-a-sig.patch` | 修正 nmxfb_vtrace 环的下标，不再用有符号取模 | 忽略 | 0034 | 不移植 | 无 |
| `0038-NMXVGAFB-virtio-gpu-EDID-16000-entry-blobs-two-comma.patch` | 读 virtio EDID，blob scatter 允许 16000 项，SET_SCANOUT_BLOB 和 fenced flush 一批提交 | 忽略 | 0008 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0039-NMXVGAFB-the-host-window-s-mode-with-its-EDID-a-time.patch` | 模式用主机窗口尺寸和 EDID 详细时序，VBL 跑在 time-constraint 线程上 | 忽略 | 0038 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0040-NMXVGAFB-virtio-gpu-display-events-ride-out-host-sta.patch` | 传递 virtio 显示变化事件；命令停住时最多等 30 秒，而不是关掉 virtio-gpu | 忽略 | 0033 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0041-NMXVGAFB-the-mode-follows-the-host-window.patch` | 显示事件到来时把主机窗口的新尺寸广告成模式 | 忽略 | 0040 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0042-NMXVGAFB-complete-WindowServer-s-To_Accelerated-so-C.patch` | 第一帧显示后再广告一次当前模式，WindowServer 离开 To_Accelerated，CoreDisplay 不再每帧重建色彩 LUT | 裸机需要 | 桌面已出现 | 中 | kexts/XeGfxIntelFB。若桌面仍在跑软件色彩再做 |
| `0043-plugin-binding-mask-skips-binding-numbers-outside-th.patch` | SPIR-V binding 不在 set layout 里时跳过（CoreAnimation 的 [[color(n)]] 在 192–194），不再把整个 mask 清掉 | 裸机需要 | 里程碑2 | 低 | plugin/。WindowServer 管线会碰到 |
| `0044-NMXVGAFB-wait-for-the-VBL-in-steps-that-timer-coales.patch` | VBL 分步睡眠，避免内核定时器合并把唤醒推迟约 1ms | 忽略 | 0039 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0045-NMXAccel-vend-NMXGPU-s-DRM-client-for-sandboxed-proc.patch` | 加速器自己创建 DRM user client 并挂在 accelerator 上。App Sandbox 拒绝挂在 GPU kext 上的 client | 裸机需要 | 0032 | 中 | kexts/XeGfxAccel。与 libdrm 0004 一起，第一帧之后 |
| `0046-NMXVGAFB-reserve-VRAM-slots-for-WindowServer-s-displ.patch` | 启动时按最大模式预留四块连续内存，避免之后模式切换申请不到连续页 | 忽略 | 0005 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |
| `0047-NMXVGAFB-one-control-queue-batch-in-flight-at-a-time.patch` | virtio 控制队列同时只飞一个 batch，避免查询覆盖正在翻转的命令 | 忽略 | 0038 | 不移植 | 面板用 kexts/XeGfxIntelFB 和固件帧缓冲，不走 virtio-gpu |

## drm-kmod（1）

打在 freebsd/drm-kmod `c16de0f`，与本仓库的 drm-kmod 基线相同。

| 文件 | 作用 | 分类 | 依赖 | 难度 | 本仓库落点 |
|---|---|---|---|---|---|
| `0001-drm_file_update_pid-no-synchronize_rcu-for-FreeBSD-s.patch` | drm_file_update_pid 在 FreeBSD 的整数 pid 上跳过 synchronize_rcu。每个新 ioctl 线程否则空等一次宽限期 | 裸机需要 | 无 | 低 | xkpi 覆盖 drm_file.c 的这一函数。第一帧之后 |

## libdrm（5）

打在 libdrm `b97cbde` 加 NullMoth 的 `libdrm-macos.patch` 之后。

| 文件 | 作用 | 分类 | 依赖 | 难度 | 本仓库落点 |
|---|---|---|---|---|---|
| `0001-Darwin-identify-dev-dri-clone-nodes-by-name-stat-fst.patch` | 用 cardN / renderDN 的名字识别 clone 节点。stat 给出的是每次 open 的 minor | 忽略 | 无 | 不移植 | userland/patches/libdrm-xegfx.patch 已按槽位匹配 |
| `0002-Darwin-drmNmxIoctl-a-sandbox-that-denies-device-ioct.patch` | 对设备 ioctl 返回 EPERM 时改走 IOKit user client | 忽略 | 0001 | 不移植 | libdrm-xegfx.patch 的 drmIoctl 回退 |
| `0003-Darwin-drmNmxIoctl-looks-up-its-user-client-with-the.patch` | 查找 user client 时用原始 fstat，不用会改写 st_rdev 的包装 | 忽略 | 0002 | 不移植 | 同上 |
| `0004-Darwin-drmNmxOpen-and-IOKit-only-devices-when-a-sand.patch` | 沙箱连 /dev/dri 都不允许读时，drmNmxOpen 返回绑到加速器 DRM client 的 token fd | 裸机需要 | nvidia 0045 | 高 | userland/patches/libdrm-xegfx.patch。WindowServer 之后的 App Sandbox |
| `0005-Darwin-token-fds-where-pipe-is-denied-log-sandbox-fa.patch` | pipe() 被拒绝时，token 改成 libdrm 自身文件的只读打开 | 裸机需要 | 0004 | 中 | 与 0004 一起。WebKit GPU 进程会禁 pipe |

## mesa（8）

打在 Mesa `bffd919` 加 NullMoth 的 `mesa-macos.patch` 之后。

| 文件 | 作用 | 分类 | 依赖 | 难度 | 本仓库落点 |
|---|---|---|---|---|---|
| `0001-anv-map-BOs-through-NMX_DRM_IOCTL_MMAP-on-Darwin.patch` | ANV 的 xe KMD backend 在 Darwin 上用 NMX_DRM_IOCTL_MMAP 映射 BO | 裸机需要 | 内核 mmap ioctl | 中 | userland/patches/mesa-xegfx.patch 目前只改了 i915 backend |
| `0002-anv-Darwin-ioctls-through-drmNmxIoctl-read-only-node.patch` | ANV ioctl 走 drmNmxIoctl；沙箱拒绝写打开时改为只读打开节点 | 忽略 | libdrm 0002 | 不移植 | mesa-xegfx.patch 已让 intel_ioctl 走 drmIoctl |
| `0003-util-anon_file-Darwin-per-user-temp-dir.patch` | 匿名文件用每用户临时目录，不用共享的 /tmp 路径 | 忽略 | 无 | 不移植 | mesa-xegfx.patch 已改 anon 文件目录 |
| `0004-anv-Darwin-integrated-GPUs-use-the-cached-coherent-P.patch` | 核显 host-visible BO 用 cached coherent PAT；ver>=20 时只有设了 ANV_XE2_COMPRESS 才打开压缩 | 裸机需要 | 无 | 低 | PAT 已在 mesa-xegfx.patch。补上 ANV_XE2_COMPRESS 这一行，默认不压缩 |
| `0005-anv-Darwin-maps-a-slab-entry-through-one-map-of-its-.patch` | 池化 BO 映射其 slab 父对象一次，子项从这块映射里取 | 裸机需要 | 0001 | 中 | ANV xe/i915 backend。第一帧之后的映射开销 |
| `0006-anv-batch-BOs-come-from-the-batch-BO-pool-on-Darwin.patch` | Darwin 上 batch BO 的分配标志不能进 slab，改从 batch BO 池取 | 裸机需要 | 无 | 低 | ANV。与 0005 一起 |
| `0007-vulkan-entrypoint-stubs-on-Apple-instead-of-flat-nam.patch` | 可选 Vulkan 入口在 Apple 上用本地弱符号桩，避免 dyld 对每个 flat namespace 导入搜遍已加载镜像 | 裸机需要 | 无 | 中 | Mesa 的 Vulkan 入口链接。进程启动变慢时再做 |
| `0008-anv-Darwin-node-opens-through-drmNmxOpen.patch` | 用 drmNmxOpen 打开节点，沙箱看不见 /dev/dri 时仍能得到设备 | 裸机需要 | libdrm 0004 | 低 | ANV 的打开路径，与 libdrm 0004 一起 |

## qemu（4）

打在 QEMU 11.1.2。物理机不使用。

| 文件 | 作用 | 分类 | 依赖 | 难度 | 本仓库落点 |
|---|---|---|---|---|---|
| `0002-edid-fit-high-refresh-modes-in-base-block.patch` | QEMU EDID 用 reduced blanking，把 120Hz 放进基础块 | 忽略 | 无 | 不移植 | 物理面板的 EDID 来自屏本身 |
| `0006-ui-gtk-egl-present-guest-frames-immediately.patch` | GTK EGL 呈现客户帧时不等 eglSwapBuffers 的 vblank | 忽略 | 无 | 不移植 | 无 QEMU |
| `0007-virtio-gpu-fenced-flushes-complete-when-shown.patch` | fenced blob RESOURCE_FLUSH 推迟到 GTK 在刷新锁存点把帧显示出来 | 忽略 | 0006 | 不移植 | 无 |
| `0008-virtio-gpu-reuse-blob-scanout-dmabufs.patch` | 按 blob 资源缓存扫描 dmabuf，翻转时不再重新 import | 忽略 | 无 | 不移植 | 无 |
