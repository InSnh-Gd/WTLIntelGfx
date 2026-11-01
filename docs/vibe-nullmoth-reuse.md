# vibe-nullmoth-xe3-qemu：WTL Panther Lake 可复用成果核查

核查日期：2026-11-01。用途：为本项目的 Panther Lake 裸机移植提取已有实现，明确 M1 之后的实际缺口。逐补丁目录仍见 [nullmoth-patch-triage.md](nullmoth-patch-triage.md)，总体阶段见 [panther-lake-xe-port-plan.md](panther-lake-xe-port-plan.md)。本文补充当前代码对照，不把旧分类表中的“裸机需要”当成尚未实现清单。

- 参考仓库：[ericek111/vibe-nullmoth-xe3-qemu][V]，固定提交 `7246d386e94a2f5e8fe4f8a17099d11514b0ae40`；本次远端 HEAD 查询仍为此提交。
- 本地参考源码：`/home/gdzzc/src/vibe-nullmoth-xe3-qemu`，包含全部补丁。
- 对照 WTL：`83cb008d0989d530a1f3c82928ab08f8533a1d9e`，工作区 `WTLIntelGfx-ptl`；该提交已包含 macOS 构建验证记录，不能继续沿用早期“尚未链接”的描述。
- 已在上述基线上完成下列源码移植及主机验证；没有运行 VF/PF 硬件测试。第 2 节记录接手时的差异，本段记录当前集成结果。

## 本次已集成

| 参考成果 | 本项目实现 | 验证范围 |
|---|---|---|
| xkpi 0048 | 新增 `0158-xe3-lrc-workarounds.patch`，回移三条 render LRC WA，保留寄存器位、MCR 属性和 IP 范围 | 干净 v6.14 应用及 xe 对象编译 |
| xkpi 0049 | 新增 `0159-guc-fence-once.patch`，等待和超时复查用 READ_ONCE，完成写入用 WRITE_ONCE | 保留原 6.14 单一 IRQ 等待；对象编译 |
| xkpi 0033/0034 | `linux/highmem.h`、`linux/page.h` 覆盖及 `xg_vm.c`：非 WB 页在 kunmap、clear_page、pmap_zero_page 后写回并失效 CPU 缓存 | WB/WC/UC、未知页、页内地址、清零及 memcpy_to_page/folio 回归 |
| xkpi 0046 | `linux_page.c` 拒绝带 `__GFP_NORETRY` 的高阶连续分配 | order 1-10 不进入分配器；order 0、DMA32 和正常高阶请求保留原路径 |
| Mesa 0001 所需的完整 BO 通路 | `xg_i915_map.c` 按 KMD 选择 BO 实现；xe 构建编入此文件及通用 `xg_drm_sync.c`，stage 4 注册；Mesa xe backend 复用 libdrm 的 map/unmap 记录 | 授权、子区间边界、页固定、迁移等待、失败回收及释放测试；未运行实际 IOKit 用户映射 |
| Mesa 0004 的压缩策略 | Darwin Xe2+ 默认关闭压缩，使用布尔选项 `ANV_XE2_COMPRESS` 显式开启 | 补丁在固定 Mesa 提交上应用成功；未重建 ANV dylib |

映射桥同时提供 GET_PCIINFO 和 BO/syncobj fence ioctls。映射记录持有 GEM 引用及 TTM pin，IOKit 映射释放后才 unpin/put。仅等待 `DMA_RESV_USAGE_KERNEL` 迁移 fence，遵循 TTM 的 CPU fault 行为；不等待全部应用提交 fence。当前仅接受原生 system-memory BO，拒绝 imported/VRAM/stolen 对象及固定地址映射。Darwin 的 `VK_EXT_map_memory_placed` 和相关 feature 已关闭，与桥的实际能力保持一致。

文件关闭清理移到 `_fdrop` 的最终引用释放点：进行中的 ioctl 仍持有文件引用，不能在它尚未插入映射记录时提前清理。此修复同样保护 i915。

主机验证结果：xe **342/342**、i915 **422/422** C 对象交叉编译通过，两个许可证检查均无未批准输入，无重复 strong symbol；新引入的映射/缓存 API 均在 C 对象集合内解析。C 侧仍有既有 XNU/内核导入，不能据此称最终 kext 已链接。**16/16** 主机测试通过，含 5 项新增回归，实际抽取 C 函数并启用 undefined-behavior sanitizer。日志位于 `out/verify/final-objects.log`、`out/verify/host-tests.log`；精确源码版本及构建范围见 [xe-build.md](xe-build.md#vibe-integration-verification)。

## 1. 这个项目已经提供什么

作者报告在 `8086:b080` Arc B390 的一个 SR-IOV VF 上运行 macOS 26.7.1：Metal 计算、Vulkan、Apple GL-over-Metal 和 WindowServer GPU 合成都工作。记录包括百万元素计算结果精确、xe exec 往返约 0.4 ms、2880x1710@120 Hz 桌面及 Minecraft 32 fps。**这些是作者报告，本次没有独立复测。** [结果与环境][V]

这为 Linux 6.14 xe、XNU 兼容层、ANV 和 Metal 插件组合提供了实际运行参考。它绕开了裸机 PF 的本地固件上传、完整 GGTT/stolen 管理和物理显示引擎接管，不能替代 WTL 的双 GT GuC、GOP 保护、原生面板及复位验收。

仓库实际有 117 个跟踪文件：README、SERIES 和 **115 个补丁**。本次查询未发现该仓库的 issue/PR 或 release 条目。补丁分布和依赖如下，应用顺序来自作者的 [SERIES][S]：

| 系列 | 数量 | 原始基线与顺序 |
|---|---:|---|
| nvidia-macos-driver | 47 | NullMoth `d96eaca`，再应用该系列 |
| xkpi | 50 | 同一个 NullMoth 仓库的 `gpu-port/xkpi`，可在上面 47 个补丁之后应用；补丁路径相对仓库根目录 |
| drm-kmod | 1 | `c16de0f9fa` |
| libdrm | 5 | `b97cbde15c5c` + 固定 NullMoth 树的 `libdrm-macos.patch`，再应用该系列 |
| Mesa | 8 | `bffd91947ef`，26.3-devel + 同树 `mesa-macos.patch`，再应用该系列 |
| QEMU | 4 | v11.1.2，依次 0002、0006、0007、0008；编号空缺不是遗漏的依赖 |

这些是打在 NullMoth 基线上的补丁，WTL 的 shim、设备名、IOKit 客户端和插件已经不同。应复用行为并保留来源，不能把 115 个补丁整体套在 WTL 上。

## 2. 接手时的 WTL 差异与处理

| 成果 | 本次核实的 WTL 状态 | 处理方式 |
|---|---|---|
| xkpi 0006：PCI 驱动名 `drmn` | [0100](../xkpi/xe/patches/0100-drmn-ptl-probe.patch) 已有 | 已吸收，继续验证实际 attach |
| xkpi 0011：runtime PM 的 get-if-active/in-use | [0130](../xkpi/xe/patches/0130-runtime-pm-always-active.patch) 已有 | 已吸收，不能据此认定 GuC 通信已经实测 |
| xkpi 0012：一段物理连续区一个 descriptor | [xg_vm.cpp](../shim/src/xnu/xg_vm.cpp) 已用 `IOMultiMemoryDescriptor` 拼接 | 已吸收，M1 的 sparse vmap 自测覆盖其布局 |
| Mesa 0004：核显 cached-coherent PAT | [mesa-xegfx.patch](../userland/patches/mesa-xegfx.patch) 的 `anv_device_get_pat_entry` 已有同类选择 | 保留，不重复叠加 PAT 修改 |
| Mesa 0001：xe BO 的 Darwin mmap | 原来只覆盖 i915；本次已接入 xe backend 及内核映射/同步桥 | 已移植，尚需真实 BO 的 compute/draw 读回 [M1] |
| xkpi 0024：页对齐掩码 | 后续 xe 映射需检查两套 `PAGE_MASK` 定义 | 用 `(PAGE_SIZE - 1)` 表达低位对齐检查，不机械搬宏名 |
| Mesa 0004：Xe2+ 压缩默认关闭 | 本次已适配 `.compressed`，保留已有 cached-coherent PAT | 关闭默认压缩；布尔开关与上游 presence test 有意不同 [M4] |
| xkpi 0033/0034：kunmap/clear_page 写出非 WB 页的脏缓存行 | 本次已补 highmem/page 覆盖及本地 VM flush | 主机测试通过，仍需大 buffer fill/upload 硬件回归 [K33][K34] |
| xkpi 0048：三条 Xe3 LRC workaround | 本次新增 0158 | 保留版本范围及 render-only 条件 [K48] |
| xkpi 0049：G2H fence 的 READ_ONCE/WRITE_ONCE | 本次新增 0159 | 原始 6.14 等待点已适配，未引入 VF 轮询 [K49] |
| xkpi 0046：拒绝高阶 `__GFP_NORETRY` 分配 | 本次已提前拒绝机会性高阶分配 | 主机验证回退条件；未复测作者的性能数值 [K46] |
| libdrm 0004/0005、driver 0045：完全打不开 `/dev/dri` 时的 token fd | WTL 的 `drmXeGfxOpen` 只有 O_RDWR 到 O_RDONLY 回退，未有该 token 打开路径 | App Sandbox/WebKit 阶段的完整功能工作，不等同于已有 WindowServer ioctl 回退 [L4][L5][N45] |
| driver 0027：GL primitive restart/provoking vertex | [NVMTLGL.m](../plugin/NVMTLGL.m) 已有这两个 SPI 和能力表处理 | 已有同类实现；参考补丁改 Intel profile，本地处理 NVIDIA profile，仍需核对实际命中和语义，不能再次整体导入 |
| driver 0026/0043：descriptor set 回收及布局外 binding 处理 | 当前仍有 set 分配/释放；`nvmtl_spirv_bmask` 对某些布局外 binding 会令 `ok=0` | 桌面正确后按性能剖析适配，注意本地 framebuffer-fetch 布局已不同 [N26][N43] |
| driver 0031/0032：GL shader 翻译修复 | WTL 的 native translator 组织已不同，没有同名 `const_selector` 模块 | 以失败 AIR 样本及正确输出为依据适配；不能凭文件名判定当前一定缺功能 [N31][N32] |

### M2 不能遗漏的内核桥接

[xg_i915_map.c](../xkpi/src/i915/xg_i915_map.c) 同时处理 `'N' 0x40/0x41` 映射、GET_PCIINFO 和 `'N' 0x42/0x43` BO fence。原实现直接使用 i915 GEM 类型；本次添加独立的 xe BO 查找/固定页实现，共用 ioctl 分发、PCI 信息和映射释放列表。

[harness/score.py](../harness/score.py) 仅把 `xkpi/src/<所选模块>/` 加入相应构建；选择 xe 时不编整个 i915 模块。本次由 [build.py](../xkpi/xe/build.py) 显式加入两个共享桥文件，并定义 `XEGFX_KMD_XE`；[xg_kext.cpp](../shim/src/xnu/xg_kext.cpp) 在 xe stage 4 调用 `xg_xe_map_init()` 注册相同回调。

BO 查找、授权、pin/map/unmap/close、GET_PCIINFO 和同步桥均已接入源码及构建。实际 IOKit 映射、同步等待和 GPU 读回仍需 macOS/PTL 验证；这与主机 mock 测试分开计数。

### host-pointer 导入不是 M1 已解决的能力

当前 [xg_xe_glue.c](../xkpi/xe/src/xg_xe_glue.c) 的 `xe_hmm_userptr_populate_range()` 返回 `-EOPNOTSUPP`。固定 Mesa `bffd91947efc1932da99aca69fc540d6d4201b0c` 的 xe backend 对 `bo->from_host_ptr` 使用 `DRM_XE_VM_BIND_OP_MAP_USERPTR`，不会按普通 GEM BO 处理。[Mesa 固定源码][AX]

同时，WTL 的 [nvmtl_vk.c](../plugin/nvmtl_vk.c) 已有 `VK_EXT_external_memory_host` buffer/IOSurface 导入实现。因此“插件在 Arrow Lake 上可用”和“PTL 只需补 mmap”之间还差 userptr 支持或经过验证的复制路径。应分开验收普通 BO 的离屏 compute/draw 与宿主页/IOSurface 导入。

另一个独立限制是 `xg_xe_mm_copy_to_user/from_user` 目前总是返回所有字节未拷贝。需要异步用户地址写回的 USER_FENCE 等路径仍不可用；不能与 DRM syncobj 的完成路径混为一谈，也不能把 VF 桌面结果当成这些桩已实现的证明。

### 压缩开关的精确语义

[Mesa 0004][M4] 的条件是 `getenv("ANV_XE2_COMPRESS") != NULL`，所以设置为 `0` 也会开启压缩。本项目改用 Mesa 的 `debug_get_bool_option(..., false)`：默认关闭，`ANV_XE2_COMPRESS=0` 仍关闭，`ANV_XE2_COMPRESS=true` 才显式开启。取消变量同样关闭：

```sh
unset ANV_XE2_COMPRESS
```

## 3. 值得复用的测量和排错方法

以下数值均来自作者的 README 或提交消息，作用是指导检查，不是 WTL 的性能承诺。

| 现象 | 上游定位与实现 | 对 WTL 的价值 |
|---|---|---|
| GPU fill 或 CPU 上传读回出现大片零 | TTM 通过 WB 内核映射清理 WC 池页，脏行随后覆盖 GPU 结果；0033/0034 分别补 kunmap 和直接 clear_page | 不能只做小 buffer 或单一缓存类型测试；应重复复用池页，并覆盖大范围 fill/upload [K33][K34] |
| 桌面使用一段时间后低于 1 fps | 高阶连续分配在碎片化内存下耗时，8 MB BO 创建约 740 ms，拒绝机会性高阶分配后约 0.8 ms | 同时记录 BO 创建延迟和内存碎片化条件，避免只归咎于 GPU 提交 [K46] |
| WindowServer 可以用 GPU，Calculator/Safari 却找不到设备 | `/dev/dri` 完全被拒、IOKit provider 不匹配，或 WebKit 不能 `pipe()` 创建 token | 分开验证 WindowServer、App Sandbox、WebKit 三类客户端 [L4][L5][N45] |
| ANV 每进程加载很慢 | 作者报告可选 Vulkan 入口的平面命名空间解析耗时 0.5-3.7 s，Apple 本地弱 stub 后为 5-10 ms | Mesa 0007 是可独立评估的用户态优化，应在实际 dylib 上测量 [M7] |
| 大量小 draw 的 CPU 时间过高 | descriptor set 分配清零和无效 binding 写入；作者记录回收与 binding mask 修复 | Vulkan 队列可工作后再剖析，不在 M1 堆性能补丁 [N26][N43] |
| GL 游戏仍走软件顶点处理 | 不同类型的 vector load、常量 sampler selector 令 shader pipeline 构建失败 | 优先保存失败 AIR/SPIR-V 和翻译错误，复用 0031/0032 的失败模式 [N31][N32] |

## 4. VF 与裸机的边界

VF 路线适合调试通用 xe/LinuxKPI、VM_BIND、提交、ANV 和部分 sandbox 行为。其必要增量包括 xkpi 0001（允许识别 VF）、0007（早期 GT MMIO）、0010（IRQ 前 CT 轮询）、0038（VF reset）、0047（memirq 分发）。WTL 当前的 PF/GOP 路线没有相同前提。[VF 说明][V]

两个细节需要保留：

- `.has_sriov=true` 是能力标志，不是把任意 GPU 强制变成 VF，也不提供 macOS PF 创建 VF 的管理接口。0050 修改的是共享 PM predicate；以后 PF 开启该能力标志时也要重新评估它，不能永久按“VF 专用”排除。
- 0010 的代码实际按 IRQ 是否启用判断，并没有只限定 VF。0049 的原始 diff 又依赖它把等待点拆成两处；WTL 应保留 PF 的初始化顺序，单独移植 fence 读写。

NMXVGAFB、virtio blob、虚拟 scanout 和 QEMU 四补丁可留作将来的 VF 调试环境参考。它们不能替代 XeGfxIntelFB 的物理面板支持。作者称“零拷贝”的范围是 presented IOSurface 到虚拟扫描输出，README 同时明确 private image 到 IOSurface **每帧仍有一次 CPU copy**。[VM 显示与已知限制][V]

### 固件要求不能从 VF 反推 PF

README 要求客体安装 GuC/HuC 文件，但 Linux 6.14 的正常 VF 分支将固件标记为 PRELOADED，跳过普通 `request_firmware`，硬件初始化也直接走 `vf_uc_init_hw()`。[固件请求][UF][硬件初始化][UC]

所以该 VF 成功不能证明客体完成了 PTL 固件上传或 HuC 认证。README 的文件要求是否来自额外安装检查，本次未做无文件启动实验；WTL PF 仍需独立验证本地固件路径与双 GT 加载。

## 5. 构建和验证范围

上游用 CachyOS kernel 7.2.9 的 PF、QEMU 11.1.2、macOS 26.7.1 客体。kext、插件和 translator 在客体以 Apple clang 构建；Mesa/libdrm 在 Linux 用客体 SDK 交叉构建。作者记录 NMXGPU 不能通过 OpenCore 注入，相关 kext 安装到 Auxiliary KC。[构建说明][V] 这属于上游栈的安装事实，不自动替代 WTL 的安装方法。

仓库没有完整 VM 配置、Meson cross file、bootstrap、可运行 benchmark 工具或原始运行日志集合，SDK/FreeBSD 源树也未完全锁定。`SERIES.md` 的应用成功结论是作者记录，本次没有重新应用或编译全部 115 个补丁。

WTL 当前的 [xe-build.md](xe-build.md#macos-build-verification) 已记录另一台无 PTL GPU 的 macOS VM 完成 xe/i915 kext 编译、链接、KPI/shadow、签名验证和 11 个主机测试。那是仓库已有记录，本次没有重跑；它也明确没有加载 kext。硬件 probe、GuC、提交和渲染仍待实测。

本次完成固定 SHA、补丁统计及调用路径核查后，进一步移植了本文开头列出的工作。重新验证了 17 个 xe 补丁、两个 C 对象构建及许可证/符号检查、16 项主机测试，并在干净的固定 Mesa 树上应用了两份本地补丁。本次没有重跑 macOS kext 最终链接、签名或真实 GPU 渲染；旧版 macOS 构建记录不替本次改动背书。

上游仍明确列出无 HiDPI、无 Xe3 VideoToolbox 硬解、新 TDR 未回移、每次启动残留一次 interrupt leak 等限制。README 的性能数字和桌面演示不构成睡眠唤醒或 GPU hang 恢复的验收。[限制][V]

## 6. 据此安排后续工作

1. 完成 WTL M1 的 PF 硬件验收：双 GT GuC、逐引擎提交、MSI、GOP PTE/像素不变。构建成功不足以越过这一关。
2. 在 macOS 重建并链接这批改动，再用普通 BO 的 compute/draw 读回验证本次已接入的映射、同步、cached-coherent PAT 和清页路径。
3. 在真实渲染及 GuC 通信中验证已回移的三条 LRC WA 和 fence 访问；大 buffer、池页复用及碎片化条件分别测量。
4. 单独解决并验证 userptr/host-pointer 导入与实际需要的用户地址写回，之后再认定既有 Metal/IOSurface 路径可用于 PTL。
5. 桌面形成后验证 App Sandbox/WebKit；按测量决定是否引入 descriptor、slab mapping、dyld 和 GL 翻译优化。高阶分配回退已移植，延迟收益仍需实测。

[V]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/README.md
[S]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/SERIES.md
[M1]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/mesa/0001-anv-map-BOs-through-NMX_DRM_IOCTL_MMAP-on-Darwin.patch
[M4]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/mesa/0004-anv-Darwin-integrated-GPUs-use-the-cached-coherent-P.patch
[M7]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/mesa/0007-vulkan-entrypoint-stubs-on-Apple-instead-of-flat-nam.patch
[K33]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/xkpi/0033-highmem-kunmap-writes-a-non-write-back-page-s-lines-.patch
[K34]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/xkpi/0034-clear_page-writes-a-non-write-back-page-s-lines-out-.patch
[K46]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/xkpi/0046-linux_page-refuse-opportunistic-higher-order-page-al.patch
[K48]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/xkpi/0048-xe-fork-Xe3-LRC-workarounds-14026781792-22021007897-.patch
[K49]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/xkpi/0049-xe-fork-READ_ONCE-WRITE_ONCE-on-the-G2H-fence-done-f.patch
[L4]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/libdrm/0004-Darwin-drmNmxOpen-and-IOKit-only-devices-when-a-sand.patch
[L5]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/libdrm/0005-Darwin-token-fds-where-pipe-is-denied-log-sandbox-fa.patch
[N26]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/nvidia-macos-driver/0026-plugin-reuse-retired-descriptor-sets-instead-of-free.patch
[N31]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/nvidia-macos-driver/0031-translator-split-vector-loads-over-GEP-indexed-slots.patch
[N32]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/nvidia-macos-driver/0032-translator-specialize-internal-callees-for-constant-.patch
[N43]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/nvidia-macos-driver/0043-plugin-binding-mask-skips-binding-numbers-outside-th.patch
[N45]: https://github.com/ericek111/vibe-nullmoth-xe3-qemu/blob/7246d386e94a2f5e8fe4f8a17099d11514b0ae40/patches/nvidia-macos-driver/0045-NMXAccel-vend-NMXGPU-s-DRM-client-for-sandboxed-proc.patch
[AX]: https://gitlab.freedesktop.org/mesa/mesa/-/blob/bffd91947efc1932da99aca69fc540d6d4201b0c/src/intel/vulkan/xe/anv_kmd_backend.c#L198-246
[UF]: https://github.com/torvalds/linux/blob/38fec10eb60d687e30c8c6b5420d86e8149f7557/drivers/gpu/drm/xe/xe_uc_fw.c#L665-L700
[UC]: https://github.com/torvalds/linux/blob/38fec10eb60d687e30c8c6b5420d86e8149f7557/drivers/gpu/drm/xe/xe_uc.c#L181-L195
