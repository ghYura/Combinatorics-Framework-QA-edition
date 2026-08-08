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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""Upload a .rec through the real GUI and persist Firefox playback evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time


SELENIUM_ROOT = Path("/tmp/sieve3d-browser")
if str(SELENIUM_ROOT) not in sys.path:
    sys.path.insert(0, str(SELENIUM_ROOT))

from selenium import webdriver  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.firefox.options import Options  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402


SAMPLE_JS = r"""
const s = window.__SIEVE3D_ACCEPTANCE_STATE;
const canvas = document.getElementById("v3");
const ctx = canvas.getContext("2d");
const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
let h = 2166136261 >>> 0;
let nonblank = 0;
const stride = Math.max(4, Math.floor(data.length / 24000 / 4) * 4);
for (let i = 0; i < data.length; i += stride) {
  const rgba = ((data[i] << 24) ^ (data[i+1] << 16) ^
                (data[i+2] << 8) ^ data[i+3]) >>> 0;
  h ^= rgba;
  h = Math.imul(h, 16777619) >>> 0;
  if (data[i+3] && (data[i] || data[i+1] || data[i+2])) nonblank++;
}
return {
  body_z: s.bodyZ,
  pose: Object.assign({}, s.pose || {}),
  selected_body: s.built && s.built.bodies[s.selBody]
    ? s.built.bodies[s.selBody].name : null,
  selected_hole: s.built && s.built.sieve.holes[s.selHole]
    ? s.built.sieve.holes[s.selHole].name : null,
  animation_playing: !!(s.anim && s.anim.playing),
  animation_frame_z: s.animFrame ? s.animFrame.z : null,
  toast: document.getElementById("toast").textContent,
  toast_class: document.getElementById("toast").className,
  progress: document.getElementById("progressText").textContent,
  canvas_width: canvas.width,
  canvas_height: canvas.height,
  canvas_hash: ("00000000" + h.toString(16)).slice(-8),
  sampled_nonblank_pixels: nonblank,
};
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rounded(value):
    if value is None:
        return None
    return round(float(value), 6)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8642/")
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-body", required=True)
    parser.add_argument("--expected-status", default="passed")
    parser.add_argument("--expected-pct", type=float, default=100.0)
    parser.add_argument("--require-motion-frames", action="store_true")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()

    record = args.record.resolve()
    if not record.is_file():
        raise SystemExit(f"record does not exist: {record}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    screenshot = args.output_dir / "replay_final.png"

    options = Options()
    options.add_argument("-headless")
    options.binary_location = "/usr/sbin/firefox"
    driver = webdriver.Firefox(options=options)
    samples = []
    finished_toast = None
    job = {}
    experiment = {}
    try:
        driver.set_window_size(1440, 1000)
        driver.get(args.url)
        def bridge_ready(current_driver):
            return current_driver.execute_script(r"""
              if (!window.__SIEVE3D_ACCEPTANCE_STATE) {
                const bridge = document.createElement('script');
                bridge.textContent =
                  'window.__SIEVE3D_ACCEPTANCE_STATE = S;';
                document.documentElement.appendChild(bridge);
                bridge.remove();
              }
              return document.readyState === 'complete' &&
                !!window.__SIEVE3D_ACCEPTANCE_STATE &&
                !!window.__SIEVE3D_ACCEPTANCE_STATE.built &&
                !!document.getElementById('fileReplay');
            """)
        WebDriverWait(driver, 20).until(bridge_ready)
        driver.find_element(By.ID, "fileReplay").send_keys(str(record))

        started = time.monotonic()
        saw_running = False
        while time.monotonic() - started < args.timeout:
            sample = driver.execute_script(SAMPLE_JS)
            sample["elapsed_s"] = round(time.monotonic() - started, 3)
            sample["body_z"] = rounded(sample.get("body_z"))
            sample["animation_frame_z"] = rounded(
                sample.get("animation_frame_z"))
            sample["pose"] = {
                key: rounded(value) for key, value in
                (sample.get("pose") or {}).items()
            }
            samples.append(sample)
            toast = sample.get("toast") or ""
            if (sample.get("animation_playing") or "replay" in (
                    sample.get("progress") or "").lower()):
                saw_running = True
            if "finished:" in toast and "clean" in toast:
                finished_toast = toast
                break
            time.sleep(0.12)
        driver.save_screenshot(str(screenshot))
        job = driver.execute_async_script("""
          const done = arguments[arguments.length - 1];
          fetch('/api/job').then(r => r.json()).then(done)
            .catch(e => done({fetch_error: String(e)}));
        """)
        experiment = driver.execute_async_script("""
          const done = arguments[arguments.length - 1];
          fetch('/api/v1/experiment').then(r => r.json()).then(done)
            .catch(e => done({fetch_error: String(e)}));
        """)
    finally:
        driver.quit()

    result = job.get("result") or {}
    state = ((experiment.get("data") or {}).get("bodies") or {}).get(
        args.expected_body) or {}
    z_values = {sample["body_z"] for sample in samples
                if sample.get("body_z") is not None}
    frame_z_values = {sample["animation_frame_z"] for sample in samples
                      if sample.get("animation_frame_z") is not None}
    pose_values = {json.dumps(sample.get("pose") or {}, sort_keys=True)
                   for sample in samples}
    canvas_hashes = {sample.get("canvas_hash") for sample in samples
                     if sample.get("canvas_hash")}
    motion_frames = int(result.get("motion_frames") or 0)
    checks = {
        "finished_toast_observed": finished_toast is not None,
        "running_state_observed": saw_running,
        "replay_job_done": job.get("status") == "done",
        "replay_clean": result.get("clean") is True,
        "api_calls_positive": int(result.get("api_calls") or 0) > 0,
        "motion_frames_requirement": (
            not args.require_motion_frames or motion_frames > 0),
        "body_z_changed": len(z_values | frame_z_values) > 1,
        "pose_or_z_changed": len(pose_values) > 1 or len(
            z_values | frame_z_values) > 1,
        "canvas_changed": len(canvas_hashes) > 1,
        "canvas_nonblank": max((sample.get("sampled_nonblank_pixels") or 0
                                for sample in samples), default=0) > 0,
        "final_body_present": bool(state),
        "final_status_exact": state.get("status") == args.expected_status,
        "final_passed_pct_exact": abs(float(state.get("passed_pct") or 0.0) -
                                      args.expected_pct) <= 1e-9,
        "screenshot_written": screenshot.is_file() and screenshot.stat().st_size > 0,
    }
    report = {
        "schema_version": "sieve3d-browser-replay-acceptance/2",
        "browser": "Firefox headless via Selenium",
        "url": args.url,
        "record_path": str(record),
        "record_sha256": sha256(record),
        "record_size_bytes": record.stat().st_size,
        "screenshot_path": str(screenshot.resolve()),
        "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
        "finished_toast": finished_toast,
        "unique_body_z_count": len(z_values),
        "unique_animation_frame_z_count": len(frame_z_values),
        "unique_pose_count": len(pose_values),
        "unique_canvas_hash_count": len(canvas_hashes),
        "sample_count": len(samples),
        "job": job,
        "final_expected_body_state": state,
        "checks": checks,
        "verdict": all(checks.values()),
        "samples": samples,
    }
    report_path = args.output_dir / "browser_replay_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "verdict": report["verdict"],
        "report": str(report_path.resolve()),
        "sample_count": len(samples),
        "unique_body_z_count": len(z_values),
        "unique_animation_frame_z_count": len(frame_z_values),
        "unique_canvas_hash_count": len(canvas_hashes),
        "finished_toast": finished_toast,
        "checks": checks,
    }, indent=2, sort_keys=True))
    return 0 if report["verdict"] else 6


if __name__ == "__main__":
    raise SystemExit(main())
