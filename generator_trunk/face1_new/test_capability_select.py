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

"""Exercise the real NiceGUI option model and run-center rendering."""

import pytest

pytest.importorskip('nicegui', reason='EXPECTED_OPTIONAL: Face 1 UI needs NiceGUI')

from nicegui import Client, ui
from nicegui.page import page

from face1_new.grid_model import GridProject
from face1_new.run_ui import _CapabilitySelect, _dimension_choices, render_run_center


@pytest.fixture
def ui_client():
    client = Client(page('/'))
    try:
        with client:
            yield client
    finally:
        client.delete()


def _option(control, value):
    index = list(control.options).index(value)
    return next(option for option in control.props['options'] if option['value'] == index)


def test_capability_values_use_real_nicegui_selection_model(ui_client):
    control = _CapabilitySelect(_dimension_choices(
        'language', encode=lambda value: 'py' if value == 'python' else value,
        selection={'language': 'python', 'execution_policy': 'generated-default'}),
        value='py')
    assert control.value == 'py'
    assert control.props['model-value']['label'] == 'Python'
    assert _option(control, 'py')['disable'] is False


def test_context_changes_preserve_selection_and_update_disabled_options(ui_client):
    control = _CapabilitySelect(_dimension_choices(
        'candidate_sink', selection={'language': 'python', 'execution_policy': 'generated-default'}),
        value='loose-files')
    assert _option(control, 'grpc')['disable'] is True
    assert 'GRPC_REQUIRES_JAVA' in _option(control, 'grpc')['label']

    control.set_capability_options(_dimension_choices(
        'candidate_sink', selection={'language': 'java', 'execution_policy': 'trusted-local'}))
    assert control.value == 'loose-files'
    assert _option(control, 'grpc')['disable'] is False
    control.set_value('grpc')
    assert control.value == 'grpc'
    assert control.props['model-value']['label'] == 'gRPC live'

    control.update()
    assert _option(control, 'grpc')['disable'] is False


def test_default_run_center_renders_and_context_callbacks_update_real_options(ui_client):
    state = {'project': GridProject.blank()}
    render_run_center(state)
    controls = {element.props['label']: element for element in ui_client.elements.values()
                if isinstance(element, _CapabilitySelect)}
    assert len(controls) == 4
    language = controls['Candidate language']
    transport = controls['Candidate transport']
    profile = controls['Execution policy · required']
    assert language.value == 'py'
    assert profile.value is None
    assert _option(transport, 'grpc')['disable'] is True

    profile.set_value('trusted-local')
    language.set_value('java')
    assert state['runtime_config']['lang'] == 'java'
    assert _option(transport, 'grpc')['disable'] is False
    transport.set_value('grpc')
    assert state['runtime_config']['transport'] == 'grpc'


def test_surface_inventory_counts_select_subclasses_and_their_labels(tmp_path):
    from face1_new.e2e.surface_contract import scan_surface

    source = tmp_path / 'surface.py'
    source.write_text('''
from nicegui import ui
class Choice(ui.select):
    pass
class FurtherChoice(Choice):
    pass
class Unrelated:
    pass
ui.select({'py': 'Python'}, value='py', label='Direct choice')
Choice({'py': 'Python'}, value='py', label='Adapted choice')
FurtherChoice({'py': 'Python'}, value='py', label='Inherited choice')
Unrelated(label='Other object')
''')
    inventory = scan_surface([source])
    assert inventory.calls['select'] == 3
    assert inventory.static_labels['select'] == frozenset({
        'Direct choice', 'Adapted choice', 'Inherited choice',
    })
