"""Prepare Linux 6.14 xe and evaluate its kbuild source list.

Source parser from NullMoth nvidia-macos-driver d96eaca gpu-port/xkpi/xesrc.py.
"""
import pathlib
import re
import shutil
import subprocess
import sys


def prepare(root, src):
    root, src = pathlib.Path(root), pathlib.Path(src)
    xe = root / 'out/xe-src'
    port = root / 'xkpi/xe'
    shutil.rmtree(xe, ignore_errors=True)
    shutil.copytree(src / 'linux/drivers/gpu/drm/xe', xe,
                    ignore=shutil.ignore_patterns('tests'))
    # Quoted includes search the source directory first: remove only the headers
    # replaced by our trace/telemetry stubs, never the upstream walker/cursor.
    for name in ['xe_trace.h', 'xe_trace_bo.h', 'xe_trace_guc.h', 'xe_trace_lrc.h', 'xe_vsec.h']:
        (xe / name).unlink()
    i915 = root / 'out/i915'
    if not i915.is_symlink():
        i915.symlink_to(src / 'drm-kmod/drivers/gpu/drm/i915', target_is_directory=True)
    subprocess.run([sys.executable, str(port / 'fork_xe.py'), str(xe)], check=True)
    for patch in sorted((port / 'patches').glob('*.patch')):
        subprocess.run(['patch', '-p1', '-i', str(patch)], cwd=xe, check=True)
    gen = root / 'out/xe-gen'
    (gen / 'generated').mkdir(parents=True, exist_ok=True)
    devres = src / 'freebsd/sys/compat/linuxkpi/common/src/linux_devres.c'
    (gen / 'linux_devres.c').write_text(
        devres.read_text() + (port / 'devres-release.inc').read_text())
    subprocess.run(['cc', '-O2', '-o', str(gen / 'xe_gen_wa_oob'),
                    str(xe / 'xe_gen_wa_oob.c')], check=True)
    for rules in sorted(xe.glob('*wa_oob.rules')):
        stem = rules.stem
        subprocess.run([str(gen / 'xe_gen_wa_oob'), str(rules),
                        str(gen / 'generated' / (stem + '.c')),
                        str(gen / 'generated' / (stem + '.h'))], check=True)


def sources(root, src, kcfg):
    root, src = pathlib.Path(root), pathlib.Path(src)
    xe = root / 'out/xe-src'
    i915 = src / 'drm-kmod/drivers/gpu/drm/i915'
    kcfg = set(kcfg) | {'DRM_XE', 'DRM_XE_DISPLAY'}
    stack, out, buf = [True], [], ''
    for raw in (xe / 'Makefile').read_text().splitlines():
        line = raw.split('#', 1)[0].strip()
        if line.endswith('\\'):
            buf += line[:-1] + ' '
            continue
        line, buf = buf + line, ''
        m = re.match(r'(ifeq|ifneq)\s*\(\$\(CONFIG_([A-Z0-9_]+)\),\s*y\)', line)
        if m:
            v = m[2] in kcfg
            stack.append(stack[-1] and (v if m[1] == 'ifeq' else not v))
            continue
        m = re.match(r'ifdef\s+CONFIG_([A-Z0-9_]+)', line)
        if m:
            stack.append(stack[-1] and m[1] in kcfg)
            continue
        if line.startswith('else'):
            prev = stack.pop()
            stack.append(stack[-1] and not prev)
            continue
        if line.startswith('endif'):
            stack.pop()
            continue
        if not stack[-1]:
            continue
        m = re.match(r'xe-(y|\$\(CONFIG_([A-Z0-9_]+)\))\s*\+?=\s*(.*)', line)
        if not m or (m[1] != 'y' and m[2] not in kcfg):
            continue
        for word in m[3].split():
            if not word.endswith('.o') or word.startswith('tests/'):
                continue
            c = word[:-2] + '.c'
            if c.startswith('i915-display/'):
                p = i915 / 'display' / c.split('/', 1)[1]
            elif c.startswith('i915-soc/'):
                p = i915 / 'soc' / c.split('/', 1)[1]
            else:
                p = xe / c
            out.append(str(p))
    drop = {l.split('#')[0].strip() for l in (root / 'xkpi/xe/exclude.txt').read_text().splitlines()}
    out.append(str(src / 'drm-kmod/drivers/gpu/drm/drm_gem_ttm_helper.c'))
    # The Darwin map ABI and GEM/syncobj bridge are shared with i915.
    out.extend(str(root / 'xkpi/src/i915' / name) for name in
               ('xg_i915_map.c', 'xg_drm_sync.c'))
    return list(dict.fromkeys(p for p in out if pathlib.Path(p).name not in drop)) + [
        str(p) for p in sorted((root / 'xkpi/xe/src').glob('*.c'))]


def flags(root, src):
    root, src = pathlib.Path(root), pathlib.Path(src)
    xe = root / 'out/xe-src'
    inc = [root / 'xkpi/xe/include', xe, root / 'out/xe-gen', xe / 'display/ext',
           xe / 'compat-i915-headers', src / 'drm-kmod/drivers/gpu/drm/i915/display']
    configs = {'DRM_XE': '1', 'DRM_XE_DISPLAY': '1', 'DRM_XE_FORCE_PROBE': '""',
               'DRM_XE_JOB_TIMEOUT_MAX': '10000', 'DRM_XE_JOB_TIMEOUT_MIN': '1',
               'DRM_XE_TIMESLICE_MAX': '10000000', 'DRM_XE_TIMESLICE_MIN': '1',
               'DRM_XE_PREEMPT_TIMEOUT': '640000', 'DRM_XE_PREEMPT_TIMEOUT_MAX': '10000000',
               'DRM_XE_PREEMPT_TIMEOUT_MIN': '1', 'DRM_XE_ENABLE_SCHEDTIMEOUT_LIMIT': '1'}
    return [v for p in inc for v in ('-I', str(p))] + [
        '-include', str(root / 'xkpi/xe/include/xg_xe_compat.h'),
        '-DXEGFX_KMD_XE=1', '-DDRM_SYSCTL_PARAM_PREFIX=_xe', '-Ddrm_i915_private=xe_device', '-DKBUILD_MODNAME="xe"', '-DLINUXKPI_PARAM_PREFIX=xe_'] + ['-DCONFIG_' + k + '=' + v for k, v in configs.items()]
