from invitation_wizard import FactorDraft, assessment, domains, propose


def test_every_domain_proposes_editable_factors_and_real_use_cases():
    for item in domains():
        draft = propose(item["id"], "find interaction defects")
        assert len(draft.factors) >= 3
        assert all(len(factor.values) >= 2 for factor in draft.factors)
        assert len(draft.interactions) >= 3
        assert len(draft.missing_constraints) >= 3
        assert draft.use_cases


def test_learning_profile_teaches_raw_and_optional_growth_honestly():
    draft = propose("learn")
    growth = assessment(draft.factors, draft.stress_actions)
    assert growth.mandatory == 48
    assert growth.optional_multiplier == 4
    assert growth.total == 192
    assert growth.interaction_pairs == 30
    assert growth.confidence == "EXACT_RAW"
    assert "forbidden combinations" in growth.missing_constraints


def test_constraints_remove_only_the_missing_relationship_warning():
    factors = (
        FactorDraft("a", "Action", ("read", "write"), ""),
        FactorDraft("b", "State", ("ready", "busy"), ""),
    )
    raw = assessment(factors)
    constrained = assessment(factors, constraints=("write requires ready",))
    assert raw.total == constrained.total == 4
    assert raw.missing_constraints
    assert constrained.missing_constraints == ()
    assert constrained.confidence == "EXACT_RAW"


def test_guardrails_flag_duplicates_singletons_and_explosion():
    factors = [
        FactorDraft(str(index), f"Factor {index}", ("same", "same") if index == 0 else ("only",), "")
        for index in range(9)
    ]
    result = assessment(factors, [FactorDraft(str(i), f"Stress {i}", ("on",), "") for i in range(5)])
    text = " ".join(result.warnings)
    assert "repeats a value" in text
    assert "fewer than two values" in text
    assert "More than eight factors" in text
    assert "Too many optional disturbances" in text


def test_risk_answers_prioritize_matching_stress_hypotheses():
    draft = propose("service", risks=("timing",))
    assert draft.stress_actions[0].risk == "timing"
    payload = draft.as_dict()
    assert payload["assessment"]["total"].isdigit()
    assert payload["assessment"]["optional_multiplier"].isdigit()
