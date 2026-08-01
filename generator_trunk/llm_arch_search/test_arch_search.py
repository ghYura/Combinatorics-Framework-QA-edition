"""Regression tests for the Transformer architecture-search suite."""

import itertools
import sys
from pathlib import Path

import pytest

# Tier classification (Prompt 03 Part C): the architecture-search suite needs
# PyTorch from the optional `ml` extra. A missing optional ML stack must present
# as a classified skip, not a collection error.
torch = pytest.importorskip(
    "torch",
    reason="EXPECTED_OPTIONAL: architecture search needs the ml extra (pip install -e '.[ml]')")
import torch.nn as nn

HERE = Path(__file__).resolve().parent
GENERATOR = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(GENERATOR))

import arch_zoo  # noqa: E402
import fwgen  # noqa: E402
import run_suite  # noqa: E402


def _explicit_linear_attention(module, x):
    batch, sequence, width = x.shape
    query, key, value = module.qkv(x).chunk(3, dim=-1)
    query = module._phi(query.view(batch, sequence, module.h, module.dh))
    key = module._phi(key.view(batch, sequence, module.h, module.dh))
    value = value.view(batch, sequence, module.h, module.dh)
    query = query.transpose(1, 2)
    key = key.transpose(1, 2)
    value = value.transpose(1, 2)
    scores = query @ key.transpose(-2, -1)
    future = torch.triu(
        torch.ones(sequence, sequence, dtype=torch.bool), diagonal=1
    )
    scores = scores.masked_fill(future, 0.0)
    normalized = scores / scores.sum(dim=-1, keepdim=True).clamp_min(1e-6)
    output = (normalized @ value).transpose(1, 2).reshape(
        batch, sequence, width
    )
    return module.out(output)


def _sparse_moe_reference(module, x):
    batch, sequence, width = x.shape
    flat = x.reshape(batch * sequence, width)
    probabilities = module.router(flat).softmax(dim=-1)
    weights, indices = probabilities.topk(module.k, dim=-1)
    weights = weights / weights.sum(dim=-1, keepdim=True).clamp_min(1e-9)
    output = torch.zeros_like(flat)
    for expert_index, expert in enumerate(module.experts):
        for rank in range(module.k):
            selected = indices[:, rank] == expert_index
            if selected.any():
                output[selected] += (
                    expert(flat[selected]) * weights[selected, rank : rank + 1]
                )
    importance = probabilities.mean(dim=0)
    load = torch.stack([
        (indices == expert_index).float().mean()
        for expert_index in range(module.ne)
    ])
    auxiliary = module.ne * (importance * load).sum()
    return output.reshape(batch, sequence, width), auxiliary


@pytest.mark.parametrize("mixer_name", sorted(arch_zoo.TOKEN_MIXERS))
def test_token_mixers_are_exactly_causal_at_every_boundary(mixer_name):
    torch.manual_seed(1)
    mixer = arch_zoo.TOKEN_MIXERS[mixer_name](8, 2, window=2).eval()
    tokens = torch.randn(1, 7, 8)
    with torch.no_grad():
        reference = mixer(tokens)
        assert torch.isfinite(reference).all()
        for cutoff in range(1, tokens.shape[1]):
            perturbed = tokens.clone()
            perturbed[:, cutoff:] += 10.0
            candidate = mixer(perturbed)
            assert torch.equal(reference[:, :cutoff], candidate[:, :cutoff])


def test_linear_attention_matches_explicit_quadratic_reference():
    torch.manual_seed(2)
    module = arch_zoo.LinearAttention(8, 2).eval()
    x = torch.randn(2, 5, 8)

    with torch.no_grad():
        recurrent = module(x)
        explicit = _explicit_linear_attention(module, x)

    assert torch.allclose(recurrent, explicit, rtol=1e-5, atol=1e-6)


def test_vectorized_moe_matches_sparse_routing_reference():
    torch.manual_seed(4)
    module = arch_zoo.MoEFFN(8, 16, num_experts=4, top_k=2).eval()
    x = torch.randn(2, 5, 8)

    with torch.no_grad():
        actual = module(x)
        actual_auxiliary = module.last_aux
        expected, expected_auxiliary = _sparse_moe_reference(module, x)

    assert torch.allclose(actual, expected, rtol=1e-5, atol=1e-6)
    assert torch.equal(actual_auxiliary, expected_auxiliary)


def test_sliding_window_contains_exactly_window_tokens():
    module = arch_zoo.SlidingWindowAttention(2, 1, window=2)
    with torch.no_grad():
        module.qkv.weight.zero_()
        module.qkv.weight[4:6].copy_(torch.eye(2))
        module.out.weight.copy_(torch.eye(2))
    x = torch.tensor([[[1.0, 0.0], [2.0, 0.0], [4.0, 0.0]]])

    output = module(x)

    assert output[0, -1, 0].item() == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("genotype", "message"),
    [
        ({"d_model": 64, "n_heads": 6}, "not divisible"),
        ({"norm": "invented"}, "unknown norm"),
        ({"token_mixer": "invented"}, "unknown token_mixer"),
        ({"channel_mixer": "invented"}, "unknown channel_mixer"),
        ({"channel_mixer": "moe", "num_experts": 1, "top_k": 2}, "top_k"),
        ({"n_layer": 3}, "unknown genotype key"),
        ({"n_layers": 0}, "n_layers must be"),
        ({"prenorm": 1}, "prenorm must be bool"),
        ({"layers": []}, "non-empty"),
        ({"layers": [{"token_mixer": "mhsa"}]}, "keys invalid"),
        ({
            "n_layers": 2,
            "layers": [
                {"token_mixer": "mhsa", "channel_mixer": "swiglu"},
            ],
        }, "disagrees with explicit layers length"),
    ],
)
def test_model_factory_fails_loud_on_incompatible_contracts(genotype, message):
    with pytest.raises(arch_zoo.GenotypeError, match=message):
        arch_zoo.build_model(genotype)


def test_explicit_layers_resolve_depth_metadata():
    model = arch_zoo.build_model({
        "layers": [
            {"token_mixer": "mhsa", "channel_mixer": "swiglu"},
            {"token_mixer": "linattn", "channel_mixer": "moe"},
            {"token_mixer": "swa", "channel_mixer": "swiglu"},
        ]
    })
    assert model.g["n_layers"] == 3
    assert len(model.blocks) == 3


def test_plugins_have_declared_parameter_effects():
    base = arch_zoo.build_model({})
    tied = arch_zoo.build_model({"tie_head": True})
    extra_norm = arch_zoo.build_model({"extra_final_norm": True})
    wide = arch_zoo.build_model({"d_ffn": 256})

    base_params = sum(p.numel() for p in base.parameters())
    tied_params = sum(p.numel() for p in tied.parameters())
    extra_params = sum(p.numel() for p in extra_norm.parameters())
    wide_params = sum(p.numel() for p in wide.parameters())

    assert tied.head.weight.data_ptr() == tied.tok.weight.data_ptr()
    assert tied_params < base_params
    assert extra_params > base_params
    assert wide_params > base_params


def test_evaluator_checks_causality_gradients_and_loss_reduction():
    metrics = arch_zoo.evaluate(
        {"token_mixer": "linattn", "channel_mixer": "moe"},
        batch=2,
        seq=8,
        benchmark_threads=1,
    )

    assert metrics["code"] == 0, metrics
    assert metrics["causal_ok"] == 1
    assert metrics["causal_checks"] == 7
    assert metrics["deterministic_ok"] == 1
    assert metrics["params"] > 0
    assert metrics["model_bytes"] == metrics["params"] * 4
    assert metrics["loss"] > 0
    assert metrics["proxy_gradnorm"] > 0
    assert 0 < metrics["grad_coverage"] <= 1
    assert 0 < metrics["nonzero_grad_coverage"] <= 1
    assert metrics["step_delta"] > 0
    assert metrics["loss_improvement"] > 0
    assert metrics["loss_after_step"] < metrics["loss"] + 5e-5
    assert metrics["latency_ms"] > 0
    assert metrics["tokens_per_s"] > 0


def test_all_grid_variants_pass_the_stronger_evaluator():
    axes = itertools.product(
        ("rmsnorm", "layernorm"),
        ("mhsa", "swa", "linattn"),
        ("swiglu", "moe"),
        (True, False),
        (2, 3),
    )
    failures = []
    for norm, token_mixer, channel_mixer, prenorm, n_layers in axes:
        genotype = {
            "norm": norm,
            "token_mixer": token_mixer,
            "channel_mixer": channel_mixer,
            "prenorm": prenorm,
            "n_layers": n_layers,
        }
        metrics = arch_zoo.evaluate(
            genotype, batch=1, seq=8, seed=3, benchmark_threads=1
        )
        if metrics["code"] != 0:
            failures.append((genotype, metrics))
    assert failures == []


def test_evaluator_detects_a_position_local_future_leak(monkeypatch):
    class LateLeak(nn.Module):
        def __init__(self, d_model, _n_heads, **_):
            super().__init__()

        def forward(self, x):
            output = torch.zeros_like(x)
            if x.shape[1] > 9:
                output[:, 8] = x[:, 9]
            return output

    monkeypatch.setitem(arch_zoo.TOKEN_MIXERS, "late_leak", LateLeak)
    metrics = arch_zoo.evaluate(
        {"token_mixer": "late_leak"}, seq=12, benchmark_threads=1
    )
    assert metrics["code"] == 4
    assert metrics["err"] == "causal_leak_at_cutoff_9"


def test_evaluator_detects_nondeterminism(monkeypatch):
    class RandomMixer(nn.Module):
        def __init__(self, _d_model, _n_heads, **_):
            super().__init__()

        def forward(self, x):
            return torch.randn_like(x)

    monkeypatch.setitem(arch_zoo.TOKEN_MIXERS, "random", RandomMixer)
    metrics = arch_zoo.evaluate(
        {"token_mixer": "random"}, seq=4, benchmark_threads=1
    )
    assert metrics["code"] == 5
    assert metrics["deterministic_ok"] == 0
    assert metrics["causal_ok"] == -1


def test_evaluator_preserves_untested_sentinels_after_nonfinite_output(monkeypatch):
    class NaNMixer(nn.Module):
        def __init__(self, _d_model, _n_heads, **_):
            super().__init__()

        def forward(self, x):
            return torch.full_like(x, float("nan"))

    monkeypatch.setitem(arch_zoo.TOKEN_MIXERS, "nan", NaNMixer)
    metrics = arch_zoo.evaluate(
        {"token_mixer": "nan"}, seq=4, benchmark_threads=1
    )
    assert metrics["code"] == 2
    assert metrics["causal_ok"] == -1
    assert metrics["deterministic_ok"] == -1


def test_unexpected_value_error_is_not_misclassified_as_domain_failure(monkeypatch):
    class BrokenMixer(nn.Module):
        def __init__(self, _d_model, _n_heads, **_):
            super().__init__()

        def forward(self, _x):
            raise ValueError("implementation bug")

    monkeypatch.setitem(arch_zoo.TOKEN_MIXERS, "broken", BrokenMixer)
    metrics = arch_zoo.evaluate(
        {"token_mixer": "broken"}, seq=4, benchmark_threads=1
    )
    assert metrics["code"] == 9
    assert metrics["err"].startswith("ValueError:implementation_bug")


def test_optimizer_noop_is_code_6(monkeypatch):
    monkeypatch.setattr(arch_zoo, "_sgd_step", lambda _model, _rate: 0.0)
    metrics = arch_zoo.evaluate({}, seq=4, benchmark_threads=1)
    assert metrics["code"] == 6
    assert metrics["step_delta"] == 0.0
    assert metrics["err"] == "optimizer_did_not_reduce_loss"


def test_nonfinite_post_step_loss_is_code_2(monkeypatch):
    def poison_step(model, _rate):
        with torch.no_grad():
            next(model.parameters()).fill_(float("nan"))
        return 1.0

    monkeypatch.setattr(arch_zoo, "_sgd_step", poison_step)
    metrics = arch_zoo.evaluate({}, seq=4, benchmark_threads=1)
    assert metrics["code"] == 2
    assert metrics["err"] == "nonfinite_post_step_loss"


def test_evaluator_rejects_vacuous_or_oversized_sequences():
    assert arch_zoo.evaluate({}, seq=1, benchmark_threads=1)["code"] == 8
    assert arch_zoo.evaluate(
        {"max_seq_len": 4}, seq=5, benchmark_threads=1
    )["code"] == 8


def test_bundle_specs_are_strict_valid_and_have_expected_cardinality(tmp_path):
    expected = {
        "arch_grid": (48, 1, 48),
        "arch_order": (6, 1, 6),
        "arch_optional": (3, 8, 24),
        "arch_compat": (9, 1, None),
    }
    for name, (mandatory, optional, final) in expected.items():
        spec_path = HERE / name / f"{name}.toml"
        spec = fwgen.load_spec(spec_path, strict=True)
        assert spec.spec_version == "1"
        plan = fwgen.spec_cardinality_plan(spec)
        assert plan.mandatory.value == mandatory
        assert plan.optional_multiplier.value == optional
        if final is None:
            assert plan.final.mode == fwgen.CardinalityMode.BOUNDED
            assert plan.final.upper == mandatory
        else:
            assert plan.final.mode == fwgen.CardinalityMode.EXACT
            assert plan.final.value == final

        workbook_path = tmp_path / f"{name}.xlsx"
        fwgen.build_compact(spec).save(workbook_path)
        assert fwgen.validate_workbook(workbook_path) == []


def test_specs_separate_transport_and_detailed_verdicts():
    for name in ("arch_grid", "arch_order", "arch_optional", "arch_compat"):
        text = (HERE / name / f"{name}.toml").read_text()
        assert "FW_VAR = 0 if _m[\"code\"] == 0 else 1" in text
        assert "FW_CUSTOM_VAR = _m[\"code\"]" in text
        assert "benchmark_threads=1" in text
        assert "loss_improvement" in text
        assert "nonzero_grad_coverage" in text


def test_compatibility_spec_declares_the_fail_loud_bond():
    spec = fwgen.load_spec(
        HERE / "arch_compat" / "arch_compat.toml", strict=True
    )
    assert len(spec.constraints) == 1
    constraint = spec.constraints[0]
    assert constraint["sheets"] == ["D_MODEL", "N_HEADS"]
    assert constraint["when"] == "D_MODEL.dm % N_HEADS.nh != 0"


def test_runner_validates_names_and_exact_defense_metric():
    assert run_suite.validate_prefix("valid-prefix.1") == "valid-prefix.1"
    assert len(run_suite.database_name("x" * 42, run_suite.DEFENSE_NAME)) == 63
    for invalid in ("", "-bad", "bad/name", "x" * 43):
        with pytest.raises(ValueError):
            run_suite.validate_prefix(invalid)

    expected = (
        "app=arch_compat d_model=64 n_heads=6 divisible=0 code=8 "
        "FW_VAR=1 FW_CUSTOM_VAR=8\n"
    )
    assert run_suite._has_expected_code_8(expected)
    assert not run_suite._has_expected_code_8("app=other code=8\n")
