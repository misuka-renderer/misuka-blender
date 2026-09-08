#!/usr/bin/env python3
"""Probe the Windows PLY / struct-jit crash described in issue #44.

Two access violations were reported on Windows, both reached through
``struct-jit.dll``: loading any PLY mesh kills the process, and
``python -c "import misuka"`` faults during interpreter shutdown. Both crash
sites touch one object, the process-wide converter cache in
``struct-jit/src/converter.cpp``. ``make_converter`` and ``clear_cache`` are
the only two ways to reach it.

This script runs each suspect in its own subprocess and reports the exit code,
so a native crash in one probe cannot hide the others.

    python scripts/win_crash_probe.py                    # every probe, misuka
    python scripts/win_crash_probe.py --module mitsuba   # upstream control
    python scripts/win_crash_probe.py --probe ply        # just one, in-process

Exit code 0 means every probe survived.
"""

import argparse
import os
import subprocess
import sys
import tempfile

PROBES = ("import", "ply", "bitmap", "drjit", "noatexit", "numpy", "crt")

# A hand-written four-vertex quad, straight from issue #44. Deliberately not
# something an exporter produced, so the file itself is never in question.
HAND_PLY = """\
ply
format ascii 1.0
element vertex 4
property float x
property float y
property float z
element face 2
property list uchar int vertex_indices
end_header
0 0 0
1 0 0
1 1 0
0 1 0
3 0 1 2
3 0 2 3
"""


def probe_import(module):
    """Symptom 2: importing alone is enough to fault on the way out.

    Nothing is rendered and no variant is selected. The fault happens during
    interpreter finalization, so this probe's own return value proves nothing.
    Only the subprocess exit code does.
    """
    __import__(module)
    print(f"imported {module} at {sys.modules[module].__file__}")


def probe_ply(module):
    """Symptom 1: instantiating a PLY shape. Reaches make_converter twice."""
    mi = __import__(module)
    mi.set_variant("scalar_rgb")

    tmp = os.path.join(tempfile.mkdtemp(), "hand.ply")
    with open(tmp, "w") as f:
        f.write(HAND_PLY)

    scene = mi.load_dict({"type": "scene", "s": {"type": "ply", "filename": tmp}})
    shape = scene.shapes()[0]
    print(f"loaded {shape.face_count()} faces, {shape.vertex_count()} vertices")


def probe_bitmap(module):
    """Reaches the same converter cache without touching PLY at all.

    Bitmap::convert calls make_converter unconditionally. If this faults too,
    the fault is the shared cache rather than anything PLY-specific.
    """
    mi = __import__(module)
    mi.set_variant("scalar_rgb")

    bmp = mi.Bitmap(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.Float32, [4, 4])
    out = bmp.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, True)
    print(f"converted {bmp.component_format()} -> {out.component_format()}")


def probe_drjit(module):
    """Import only drjit, the layer below. Does the renderer matter at all?"""
    del module
    import drjit

    print(f"imported drjit {drjit.__version__} at {drjit.__file__}")


def probe_noatexit(module):
    """Import, then drop every registered atexit callback.

    misuka registers exactly one, in src/python/main.cpp, and clear_cache() is
    inside it. If this exits cleanly while the plain import probe faults, the
    fault is in a registered callback rather than anywhere else in teardown.

    Read it in one direction only. Skipping the callback also skips misuka's
    own shutdown, which aborts on macOS and Linux, so a nonzero result here
    proves nothing. A zero result does.
    """
    import atexit

    __import__(module)
    atexit._clear()
    print(f"imported {module} and cleared every atexit callback")


def probe_numpy(module):
    """Control: an ordinary compiled extension that is not nanobind or misuka."""
    del module
    import numpy

    print(f"imported numpy {numpy.__version__}")


def probe_crt(module):
    """Report which C++ runtime the process actually loaded.

    Anaconda and Blender both ship their own msvcp140.dll next to the
    executable, which can shadow the system one. If the module was built
    against a newer toolset than the DLL that wins, the thread-safe-static
    guard in MSVCP140 is a plausible fault site.
    """
    __import__(module)

    print(f"python      {sys.version}")
    print(f"executable  {sys.executable}")
    print(f"{module:<12}{sys.modules[module].__file__}")

    try:
        import importlib.metadata as md

        print(f"version     {md.version(module)}")
    except Exception as e:  # noqa: BLE001 - diagnostics only
        print(f"version     unavailable ({e})")

    if sys.platform != "win32":
        print("\n(not Windows: no module listing)")
        return

    keywords = ("msvcp", "vcruntime", "struct-jit", "drjit", "mitsuba", "misuka")
    print(f"\n{'version':<20}{'bytes':>14}  path")
    for path in _loaded_modules():
        base = os.path.basename(path).lower()
        if any(k in base for k in keywords):
            print(f"{_file_version(path):<20}{_size(path):>14}  {path}")


def _loaded_modules():
    """Every DLL currently mapped into this process, via EnumProcessModules."""
    import ctypes
    from ctypes import wintypes

    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # Without argtypes, ctypes narrows a module handle to a C int and raises
    # OverflowError on any handle above 2 GB.
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.EnumProcessModules.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE),
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    psapi.EnumProcessModules.restype = wintypes.BOOL
    psapi.GetModuleFileNameExW.argtypes = [
        wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD,
    ]
    psapi.GetModuleFileNameExW.restype = wintypes.DWORD

    handle = kernel32.GetCurrentProcess()
    count = 4096
    array = (wintypes.HMODULE * count)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcessModules(
        handle, array, ctypes.sizeof(array), ctypes.byref(needed)
    ):
        return []

    buf = ctypes.create_unicode_buffer(32768)
    paths = []
    for i in range(min(count, needed.value // ctypes.sizeof(wintypes.HMODULE))):
        if psapi.GetModuleFileNameExW(handle, array[i], buf, len(buf)):
            paths.append(buf.value)
    return sorted(paths, key=str.lower)


def _size(path):
    try:
        return f"{os.path.getsize(path):,}"
    except OSError:
        return "?"


def _file_version(path):
    """The PE version resource, e.g. 14.44.35211.0 for a VC++ redistributable."""
    import ctypes
    from ctypes import wintypes

    class FixedFileInfo(ctypes.Structure):
        _fields_ = [
            ("dwSignature", wintypes.DWORD),
            ("dwStrucVersion", wintypes.DWORD),
            ("dwFileVersionMS", wintypes.DWORD),
            ("dwFileVersionLS", wintypes.DWORD),
            ("dwProductVersionMS", wintypes.DWORD),
            ("dwProductVersionLS", wintypes.DWORD),
            ("dwFileFlagsMask", wintypes.DWORD),
            ("dwFileFlags", wintypes.DWORD),
            ("dwFileOS", wintypes.DWORD),
            ("dwFileType", wintypes.DWORD),
            ("dwFileSubtype", wintypes.DWORD),
            ("dwFileDateMS", wintypes.DWORD),
            ("dwFileDateLS", wintypes.DWORD),
        ]

    try:
        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = [
            wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = [
            ctypes.c_void_p, wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
        version.VerQueryValueW.restype = wintypes.BOOL

        size = version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return "-"
        data = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, data):
            return "-"
        block = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not version.VerQueryValueW(
            data, "\\", ctypes.byref(block), ctypes.byref(length)
        ):
            return "-"
        info = ctypes.cast(block, ctypes.POINTER(FixedFileInfo)).contents
        ms, ls = info.dwFileVersionMS, info.dwFileVersionLS
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:  # noqa: BLE001 - diagnostics only
        return "-"


def _verdict(code):
    if code == 0:
        return "ok"
    # A Windows access violation surfaces as 3221225477, which is 0xC0000005.
    # POSIX reports a native fault as a negative signal number instead.
    if code < 0 or code > 0xFFFF:
        return f"CRASHED 0x{code & 0xFFFFFFFF:08X}"
    return "failed"


def run_all(module):
    """Run every probe twice as its own subprocess and tabulate the exit codes.

    The second run ends with ``os._exit(0)``, which skips Python finalization
    and therefore skips misuka's atexit handler, where ``clear_cache()`` lives.
    A probe that faults normally but exits cleanly with a hard exit puts the
    fault in teardown, not in the work the probe did.
    """
    # ply and bitmap are renderer plugins, and noatexit targets the renderer's
    # own atexit callback. None of them mean anything when drjit is the module
    # under test.
    probes = PROBES if module != "drjit" else ("import", "drjit", "numpy", "crt")

    results = []
    for probe in probes:
        row = [probe]
        for hard in (False, True):
            mode = "hard exit" if hard else "normal exit"
            print(f"\n{'=' * 68}\n== {probe} ({mode})\n{'=' * 68}", flush=True)
            cmd = [sys.executable, os.path.abspath(__file__),
                   "--module", module, "--probe", probe]
            if hard:
                cmd.append("--hard-exit")
            row.append(subprocess.run(cmd, check=False).returncode)
        results.append(tuple(row))

    label = os.environ.get("PROBE_LABEL", sys.platform)
    print(f"\n{'=' * 68}")
    print(f"{module} on {label}, python {sys.version.split()[0]}")
    print(f"{'probe':<10}{'normal':>12}{'hard exit':>12}  verdict")
    for probe, normal, hard in results:
        print(f"{probe:<10}{normal:>12}{hard:>12}  {_verdict(normal)}")

    _write_summary(module, label, results)
    return 0 if all(n == 0 for _, n, _ in results) else 1


def _write_summary(module, label, results):
    """Append the table to the GitHub Actions job summary, when there is one."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n### `{module}` on {label}\n\n")
        f.write(f"Python {sys.version.split()[0]}, `{sys.executable}`\n\n")
        f.write("| probe | normal exit | hard exit | verdict |\n|---|---|---|---|\n")
        for probe, normal, hard in results:
            f.write(f"| {probe} | {normal} | {hard} | {_verdict(normal)} |\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", default="misuka",
                        help="renderer module to probe (misuka or mitsuba)")
    parser.add_argument("--probe", default="all", choices=("all",) + PROBES,
                        help="run one probe in this process, or all in subprocesses")
    parser.add_argument("--hard-exit", action="store_true",
                        help="leave through os._exit(0), skipping finalization")
    args = parser.parse_args()

    if args.probe == "all":
        return run_all(args.module)

    import faulthandler

    faulthandler.enable()
    globals()[f"probe_{args.probe}"](args.module)

    if args.hard_exit:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
