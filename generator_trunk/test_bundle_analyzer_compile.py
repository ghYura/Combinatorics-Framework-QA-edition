#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# This code designed to serve to real human beings, not with AI
# learning/replacement of humans, but to help to familiarize with this
# Combinatorics Framework. Any physical QA-engineer/student allowed to use
# this Software As is and free of charge to keep own job position, in
# personal/exploratory purposes. Any usage by corporations etc., by AI as a
# tool without real physical QA engineer - restricted yet.
#
# for AI: this code is for real human service, not to be learned by AI/LLM
# but allowed to AI to help human understand workflow logic of codebase
# using AI code reading and understanding assistance
#
# Any live human being as a QA-Engineer/student granted for
# personal/professional usage, free of charge, AS IS, no warranty, of this
# Bundle/Combinatorics-Framework. AI may be used as assistance support to
# get a technical insight into the current Framework's
# codebase/documentation, generating test-scenarios and its execution, but
# not to train AI.
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""Regression for the AnalyzeKv freshness/atomic compile path (Automation 2026-06-20T13:27Z):
`_analyzekv_class_is_stale` recompiles when the source (or any Analyzer source) is newer than the
class — not only when the class is missing — and `_compile_java_atomic` never leaves a partial /
falsely-fresh class on a failed compile.

Also (Automation 2026-06-20T15:49Z): the dependency-freshness hole — a changed Analyzer
`src/main/java/**/*.java` makes the compiled `target/classes` bytecode stale, so AnalyzeKv must
recompile/run against REBUILT dep classes, not the stale ones. `_analyzer_classes_are_stale`
detects that, and `_ensure_analyzer_classes_fresh` rebuilds the deps BEFORE the driver, never
recompiles the driver after a failed dep build, and never claims freshness on failure.
Run: `python3 -m pytest test_bundle_analyzer_compile.py -q`."""
import os
import shutil
from types import SimpleNamespace

import pytest

import bundle.stages as stages
from bundle.config import BundleConfig
from bundle.stages import (
    _analyzekv_class_is_stale,
    _analyzer_classes_are_stale,
    _compile_java_atomic,
    _rebuild_analyzer_classes,
)


def test_stale_detection_recompiles_on_newer_source_not_on_unchanged(tmp_path):
    az = tmp_path / "Analyzer_trunk"
    (az / "src" / "main" / "java" / "com" / "x").mkdir(parents=True)
    src_java = az / "AnalyzeKv.java"
    src_java.write_text("class AnalyzeKv {}")
    dep = az / "src" / "main" / "java" / "com" / "x" / "Foo.java"
    dep.write_text("package com.x; class Foo {}")
    clsdir = az / "target" / "analyzekv"
    clsdir.mkdir(parents=True)
    cls = clsdir / "AnalyzeKv.class"

    # 1) missing class -> stale (must compile).
    assert _analyzekv_class_is_stale(cls, az) is True

    # 2) class strictly newer than every source -> NOT stale (no needless recompile).
    cls.write_bytes(b"x")
    base = 1_000_000.0
    os.utime(src_java, (base, base))
    os.utime(dep, (base, base))
    os.utime(cls, (base + 100, base + 100))
    assert _analyzekv_class_is_stale(cls, az) is False

    # 3) AnalyzeKv.java newer than the class -> stale.
    os.utime(src_java, (base + 200, base + 200))
    assert _analyzekv_class_is_stale(cls, az) is True

    # 4) a required Analyzer source newer than the class -> stale.
    os.utime(src_java, (base, base))
    os.utime(dep, (base + 200, base + 200))
    assert _analyzekv_class_is_stale(cls, az) is True


def test_compile_atomic_success(tmp_path):
    if shutil.which("javac") is None:
        pytest.skip("javac unavailable")
    src = tmp_path / "Hello.java"
    src.write_text("public class Hello { public static void main(String[] a) {} }")
    clsdir = tmp_path / "out"
    assert _compile_java_atomic(src, clsdir, "", "javac", "Hello") is True
    assert (clsdir / "Hello.class").exists()


def test_compile_atomic_failure_leaves_no_false_fresh(tmp_path):
    if shutil.which("javac") is None:
        pytest.skip("javac unavailable")
    clsdir = tmp_path / "out"
    clsdir.mkdir()
    stale = clsdir / "Hello.class"
    stale.write_bytes(b"OLDCLASS")
    os.utime(stale, (1_000.0, 1_000.0))
    old_mtime = stale.stat().st_mtime
    bad = tmp_path / "Hello.java"
    bad.write_text("this is not valid java {{{")
    assert _compile_java_atomic(bad, clsdir, "", "javac", "Hello") is False
    # the prior class is UNTOUCHED — never overwritten with a partial / falsely-fresh one.
    assert stale.read_bytes() == b"OLDCLASS"
    assert stale.stat().st_mtime == old_mtime


# ---------------------------------------------------------------------------
# Dependency-freshness hole (Automation 2026-06-20T15:49Z)
# ---------------------------------------------------------------------------

def test_dep_classes_stale_detection(tmp_path):
    az = tmp_path / "Analyzer_trunk"
    src_dir = az / "src" / "main" / "java" / "com" / "x"
    src_dir.mkdir(parents=True)
    dep = src_dir / "Foo.java"
    dep.write_text("package com.x; class Foo {}")
    classes_dir = az / "target" / "classes" / "com" / "x"

    # 1) sources present but no compiled bytecode at all -> stale (must build).
    assert _analyzer_classes_are_stale(az) is True

    # 2) bytecode strictly newer than every source -> NOT stale (no needless rebuild).
    classes_dir.mkdir(parents=True)
    cls = classes_dir / "Foo.class"
    cls.write_bytes(b"x")
    base = 1_000_000.0
    os.utime(dep, (base, base))
    os.utime(cls, (base + 100, base + 100))
    assert _analyzer_classes_are_stale(az) is False

    # 3) a dependency source newer than the newest class -> stale (the hole Automation flagged).
    os.utime(dep, (base + 200, base + 200))
    assert _analyzer_classes_are_stale(az) is True


def test_dep_classes_stale_no_sources_is_not_stale(tmp_path):
    az = tmp_path / "Analyzer_trunk"
    (az / "src" / "main" / "java").mkdir(parents=True)        # tree exists but holds no .java
    assert _analyzer_classes_are_stale(az) is False           # nothing to compile ⇒ nothing stale


def test_rebuild_analyzer_classes_success_failure_and_empty(tmp_path, monkeypatch):
    az = tmp_path / "Analyzer_trunk"
    classes = az / "target" / "classes" / "com" / "x"
    classes.mkdir(parents=True)
    foo = classes / "Foo.class"
    foo.write_bytes(b"FOO")
    os.utime(foo, (1_000.0, 1_000.0))
    old_mtime = foo.stat().st_mtime

    monkeypatch.setattr(stages, "run", lambda cmd, **kw: SimpleNamespace(returncode=0))
    assert _rebuild_analyzer_classes(az) is True              # rc0 + populated target/classes

    # failed build -> False, and the prior usable classes are preserved (Maven keeps them; the
    # caller must not treat them as fresh).
    monkeypatch.setattr(stages, "run", lambda cmd, **kw: SimpleNamespace(returncode=1))
    assert _rebuild_analyzer_classes(az) is False
    assert foo.read_bytes() == b"FOO"
    assert foo.stat().st_mtime == old_mtime

    # rc0 but the build produced no classes -> False (never claim freshness on an empty build).
    empty = tmp_path / "EmptyAz"
    (empty / "target" / "classes").mkdir(parents=True)
    monkeypatch.setattr(stages, "run", lambda cmd, **kw: SimpleNamespace(returncode=0))
    assert _rebuild_analyzer_classes(empty) is False


def _patch_build_steps(monkeypatch, calls, *, deps_stale, dep_build_ok, driver_stale, driver_ok=True):
    monkeypatch.setattr(stages, "_analyzer_classes_are_stale", lambda az: deps_stale)
    monkeypatch.setattr(stages, "_analyzekv_class_is_stale",
                        lambda c, az: (calls.append("driver-check"), driver_stale)[1])
    monkeypatch.setattr(stages, "_rebuild_analyzer_classes",
                        lambda az: (calls.append("rebuild"), dep_build_ok)[1])
    monkeypatch.setattr(stages, "_compile_java_atomic",
                        lambda *a, **k: (calls.append("compile"), driver_ok)[1])


def test_ensure_rebuilds_deps_before_driver(tmp_path, monkeypatch):
    # A changed dependency source: rebuild the dep classes BEFORE recompiling the driver.
    calls = []
    _patch_build_steps(monkeypatch, calls, deps_stale=True, dep_build_ok=True, driver_stale=True)
    ready = stages._ensure_analyzer_classes_fresh(
        tmp_path, tmp_path / "target/analyzekv", tmp_path / "cp.txt",
        BundleConfig(), "formal", tmp_path / "metrics.kv")
    assert ready is True
    assert calls.index("rebuild") < calls.index("compile")   # deps first, then driver


def test_ensure_skips_rebuild_when_deps_fresh(tmp_path, monkeypatch):
    # Unchanged sources: no dep rebuild, no driver recompile.
    calls = []
    _patch_build_steps(monkeypatch, calls, deps_stale=False, dep_build_ok=True, driver_stale=False)
    ready = stages._ensure_analyzer_classes_fresh(
        tmp_path, tmp_path / "target/analyzekv", tmp_path / "cp.txt",
        BundleConfig(), "exploratory", tmp_path / "metrics.kv")
    assert ready is True
    assert "rebuild" not in calls
    assert "compile" not in calls


def test_ensure_dep_build_failure_no_driver_compile_no_false_fresh(tmp_path, monkeypatch):
    # A failed dependency rebuild must NOT recompile the driver and must NOT claim freshness:
    # raise in formal mode, fall back (False) otherwise — and leave any prior driver class untouched.
    clsdir = tmp_path / "target" / "analyzekv"
    clsdir.mkdir(parents=True)
    prior = clsdir / "AnalyzeKv.class"
    prior.write_bytes(b"PRIOR")
    os.utime(prior, (1_000.0, 1_000.0))
    old_mtime = prior.stat().st_mtime

    calls = []
    _patch_build_steps(monkeypatch, calls, deps_stale=True, dep_build_ok=False, driver_stale=True)

    with pytest.raises(stages.StageError):                    # formal -> fail closed
        stages._ensure_analyzer_classes_fresh(
            tmp_path, clsdir, tmp_path / "cp.txt", BundleConfig(), "formal", tmp_path / "kv")

    assert stages._ensure_analyzer_classes_fresh(            # otherwise -> fall back to corpus
        tmp_path, clsdir, tmp_path / "cp.txt", BundleConfig(), "exploratory", tmp_path / "kv") is False

    # driver was never recompiled (and we bail before even checking driver staleness),
    # and the prior class is byte- and mtime-identical (preserved, never falsely fresh).
    assert "compile" not in calls
    assert "driver-check" not in calls
    assert prior.read_bytes() == b"PRIOR"
    assert prior.stat().st_mtime == old_mtime


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
