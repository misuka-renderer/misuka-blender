#!/usr/bin/env python3
"""Probe the Windows access violations behind issues #44 and #4.

Every process that imports drjit exits with 0xC0000005 on Windows, whatever it
did in between. The fault is in Python finalization: the same probe run through
``os._exit(0)`` exits 0. ``import drjit`` on its own is enough to trigger it,
with no renderer installed, so it is an upstream drjit fault rather than
anything misuka or this add-on does.

Issue #44 also reports that loading a mesh kills the process outright. The
mesh probes write their own files rather than relying on anything committed, and
cover the four combinations of ASCII or binary against with or without texture
coordinates, so a crash can be attributed to one of them. ``scene`` runs the same
binary mesh through ``load_file`` and the XML parser instead of ``load_dict``.

Each probe runs in its own subprocess and is reported by exit code, so a native
crash in one cannot hide the others.

    python scripts/win_crash_probe.py                    # every probe, misuka
    python scripts/win_crash_probe.py --module mitsuba   # upstream control
    python scripts/win_crash_probe.py --module drjit     # minimal reproducer
    python scripts/win_crash_probe.py --probe ply        # just one, in-process

Exit code 0 means every probe survived.
"""

import argparse
import os
import subprocess
import sys
import tempfile

PROBES = ("import", "ply", "plyst", "plybin", "plybinst", "scene", "acoustic",
          "bitmap", "drjit", "noatexit", "numpy", "crt")


def write_ply(path, binary, texcoords):
    """Write a two-triangle quad, in the shape Mesh.write_ply would produce.

    The exporter always writes binary little-endian, and names its texture
    coordinates s and t, which ply.cpp renames to u and v while loading. The
    four combinations here separate "binary" from "has texture coordinates"
    as the trigger for a crash.
    """
    import struct

    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    faces = [(0, 1, 2), (0, 2, 3)]

    header = ["ply"]
    header.append("format binary_little_endian 1.0" if binary
                  else "format ascii 1.0")
    header.append(f"element vertex {len(verts)}")
    header += [f"property float {n}" for n in ("x", "y", "z")]
    if texcoords:
        header += [f"property float {n}" for n in ("s", "t")]
    header.append(f"element face {len(faces)}")
    header.append("property list uchar int vertex_indices")
    header.append("end_header")

    with open(path, "wb") as f:
        f.write(("\n".join(header) + "\n").encode("ascii"))
        for i, v in enumerate(verts):
            row = list(v) + (list(uvs[i]) if texcoords else [])
            if binary:
                f.write(struct.pack("<%df" % len(row), *row))
            else:
                f.write((" ".join("%.9g" % x for x in row) + "\n").encode("ascii"))
        for tri in faces:
            if binary:
                f.write(struct.pack("<B3i", 3, *tri))
            else:
                f.write(("3 %d %d %d\n" % tri).encode("ascii"))
    return path


def _load_ply(module, binary, texcoords):
    mi = __import__(module)
    mi.set_variant("scalar_rgb")

    path = write_ply(os.path.join(tempfile.mkdtemp(), "quad.ply"),
                     binary, texcoords)
    scene = mi.load_dict({"type": "scene", "s": {"type": "ply", "filename": path}})
    shape = scene.shapes()[0]
    print(f"loaded {shape.face_count()} faces, {shape.vertex_count()} vertices")


def probe_import(module):
    """Symptom 2: importing alone is enough to fault on the way out.

    Nothing is rendered and no variant is selected. The fault happens during
    interpreter finalization, so this probe's own return value proves nothing.
    Only the subprocess exit code does.
    """
    __import__(module)
    print(f"imported {module} at {sys.modules[module].__file__}")


def probe_ply(module):
    """ASCII, positions only. The file from issue #44."""
    _load_ply(module, binary=False, texcoords=False)


def probe_plyst(module):
    """ASCII, with s/t texture coordinates."""
    _load_ply(module, binary=False, texcoords=True)


def probe_plybin(module):
    """Binary little-endian, positions only."""
    _load_ply(module, binary=True, texcoords=False)


def probe_plybinst(module):
    """Binary little-endian with s/t. This is what the exporter writes."""
    _load_ply(module, binary=True, texcoords=True)


def probe_scene(module):
    """Load a scene from XML through load_file, as a user would.

    Goes through the XML parser rather than load_dict. The mesh is the same
    binary file the exporter produces.
    """
    mi = __import__(module)
    mi.set_variant("scalar_rgb")

    work = tempfile.mkdtemp()
    write_ply(os.path.join(work, "quad.ply"), binary=True, texcoords=True)
    xml = os.path.join(work, "scene.xml")
    with open(xml, "w") as f:
        f.write(
            '<scene version="3.0.0">\n'
            '  <shape type="ply">\n'
            '    <string name="filename" value="quad.ply"/>\n'
            '  </shape>\n'
            '</scene>\n')

    scene = mi.load_file(xml)
    print(f"loaded {len(scene.shapes())} shape(s)")


def probe_acoustic(module):
    """Load an acoustic scene of the shape the add-on exports.

    Same plugin set as a real export: an acoustic_path integrator, a microphone
    with a tape film, an acousticbsdf, and a ply mesh. This is what
    test_round_trip_acoustic loads, and what crashes inside Blender on Windows
    with 3.6, 4.2 and 4.5.
    """
    mi = __import__(module)
    mi.set_variant("scalar_rgb")

    work = tempfile.mkdtemp()
    write_ply(os.path.join(work, "quad.ply"), binary=True, texcoords=True)
    bands = ", ".join(f"{f}:0.5" for f in
                      (31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000))
    xml = os.path.join(work, "acoustic.xml")
    with open(xml, "w") as f:
        f.write(f"""<scene version="0.1.0">
    <integrator type="acoustic_path" name="integrator" id="integrator">
        <integer name="max_depth" value="-1" />
        <float name="max_energy_loss" value="90" />
        <boolean name="hide_emitters" value="false" />
        <float name="max_time" value="2" />
    </integrator>
    <sensor type="microphone" name="mic" id="mic">
        <sampler type="independent" name="sampler">
            <integer name="sample_count" value="16" />
        </sampler>
        <film type="tape" name="film">
            <integer name="time_bins" value="2000" />
            <string name="frequencies" value="31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000" />
            <rfilter type="gaussian" name="rfilter">
                <float name="stddev" value="0.25" />
            </rfilter>
        </film>
    </sensor>
    <shape type="sphere" name="emit" id="emit">
        <float name="radius" value="0.1" />
        <emitter type="area" name="emitter">
            <texture type="uniform" name="radiance">
                <float name="value" value="2533.0" />
            </texture>
        </emitter>
        <bsdf type="null" name="bsdf" />
    </shape>
    <bsdf type="twosided" id="mat" name="mat">
        <bsdf type="acousticbsdf" name="bsdf">
            <spectrum name="absorption" value="{bands}" />
            <spectrum name="scattering" value="{bands}" />
            <float name="specular_lobe_width" value="0.001" />
        </bsdf>
    </bsdf>
    <shape type="ply" name="mesh" id="mesh">
        <string name="filename" value="quad.ply" />
        <boolean name="face_normals" value="true" />
        <ref name="bsdf" id="mat" />
    </shape>
</scene>
""")

    scene = mi.load_file(xml)
    print(f"loaded {len(scene.shapes())} shapes, "
          f"sensor {str(scene.sensors()[0]).splitlines()[0]}")


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
    if module == "mitsuba":
        # acoustic_path, microphone, tape and acousticbsdf are misuka plugins.
        probes = tuple(p for p in probes if p != "acoustic")

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
        # This run exists only to read back an exit code, so faulthandler has
        # nothing useful left to say. Leaving it on prints a traceback that
        # makes a clean result look like a failure in a pasted report.
        faulthandler.disable()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
