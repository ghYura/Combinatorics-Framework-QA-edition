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

from pathlib import Path
import shutil
import subprocess

from invitation_wizard import domains


ROOT = Path(__file__).resolve().parent


def test_original_face_loads_offline_coach_and_exposes_server_endpoint():
    html = (ROOT / "intake" / "face1.html").read_text(encoding="utf-8")
    server = (ROOT / "intake" / "serve_face1.py").read_text(encoding="utf-8")
    assert '<script src="invitation_wizard.js"></script>' in html
    assert 'id="invite_domain"' in html
    assert 'id="invite_apply"' in html
    assert "invitationAssessment" in html
    assert '"/api/invitation"' in server


def test_browser_catalog_tracks_shared_domain_ids_and_teaching_sut():
    script = (ROOT / "intake" / "invitation_wizard.js").read_text(encoding="utf-8")
    for item in domains():
        assert f"{item['id']}:" in script
    assert "$BUNDLE_SUT_ROOT/combination_thinking_tutor" in script


def test_face1_new_starts_with_confirm_before_apply_coach():
    app = (ROOT / "face1_new" / "app.py").read_text(encoding="utf-8")
    ui = (ROOT / "face1_new" / "invitation_ui.py").read_text(encoding="utf-8")
    assert 'ui.tab("Guided start")' in app
    assert "render_invitation_center(state, apply_guided_project)" in app
    assert "Nothing is applied silently" in ui
    assert "project_from_invitation" in ui


def test_browser_catalog_has_valid_javascript_when_node_is_available():
    node = shutil.which("node")
    if node:
        subprocess.run(
            [node, "--check", str(ROOT / "intake" / "invitation_wizard.js")],
            check=True,
            capture_output=True,
            text=True,
        )
