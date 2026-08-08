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

"""The genetics model and its oracle: the properties any later study would rest on.

These are not "does it run" tests. Each one locks a property that, if it silently
stopped holding, would make a future comparison study meaningless without
anything looking broken:

* the scientific boundary is stated in the code, not only in a document;
* each oracle/verdict layer is reachable, and executable checks do not judge
  outputs by re-running the same implementation;
* the interaction terms are *reachable and non-additive*, or there is nothing for
  combinatorial construction to find;
* the viability contract can actually fire — a contract that never fires is
  decoration, which is exactly the trap the second flagship SUT fell into;
* the model performs no I/O and reaches no external data.
"""
from __future__ import annotations

import ast
import itertools
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from generator_trunk.genetics_model_testing import expert_model            # noqa: E402
from generator_trunk.genetics_model_testing.model import environment as env  # noqa: E402
from generator_trunk.genetics_model_testing.model import genome as g        # noqa: E402
from generator_trunk.genetics_model_testing.model import operations as ops   # noqa: E402
from generator_trunk.genetics_model_testing.model import oracle as orc       # noqa: E402

MODEL_DIR = HERE / "model"


def _genotype(states):
    """A genotype from per-locus (left, right) allele pairs."""
    return g.Genotype(g.Haplotype(tuple(s[0] for s in states)),
                      g.Haplotype(tuple(s[1] for s in states)))


def _apply_both(operations, genotype=None):
    genotype = genotype or g.homozygous_reference()
    left, right = genotype.left, genotype.right
    for operation in operations:
        left, right = ops.apply_pair(operation, left, right)
    return g.Genotype(left, right)


# ------------------------------------------------ the scientific boundary ----
class TestTheScientificBoundaryIsStatedInTheCode(unittest.TestCase):
    """R1 in docs/37: the boundary must live where someone reading the code will
    see it, not only in a document they may never open."""

    #: The exact marker every model module must carry. A stable string, not a
    #: fuzzy phrase match: the first version of this test looked for any of three
    #: hand-written sentences and passed modules that said nothing at all.
    BOUNDARY_MARKER = "MODELLED REPRESENTATIONS ONLY: not human DNA"

    def test_every_model_module_states_that_it_is_not_biology(self):
        for path in sorted(MODEL_DIR.glob("*.py")):
            if path.name == "__init__.py":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIn(self.BOUNDARY_MARKER, text,
                          f"{path.name} does not carry the boundary marker")

    def test_the_readme_states_the_boundary_before_anything_else(self):
        # Whitespace-normalized: the sentence wraps in the source, and the first
        # version of this test failed on its own document for that reason.
        raw = (HERE / "README.md").read_text(encoding="utf-8")
        readme = " ".join(raw.split())
        boundary = readme.index("not human DNA")
        contents = readme.index("## What is here")
        self.assertLess(boundary, contents, "the boundary must come first")

    def test_the_model_reaches_no_external_data(self):
        """R4: no real DNA, no external source. Asserted structurally rather than
        by convention, so filling in the D7 seam cannot quietly break it."""
        forbidden = {"open", "urlopen", "requests", "socket", "urllib", "httpx",
                     "subprocess", "read_text", "read_bytes", "loadtxt"}
        for path in sorted(MODEL_DIR.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], forbidden, path.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], forbidden, path.name)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden, f"{path.name}: {node.func.id}")


# --------------------------------------------------------- genetic objects ---
class TestGeneticObjects(unittest.TestCase):
    def test_a_genotype_is_unordered(self):
        """Diploid pairs have no first and second chromosome. If this regresses,
        every count over the genotype space silently doubles."""
        a = g.Haplotype((0,) * 12)
        b = g.Haplotype((2,) + (0,) * 11)
        self.assertEqual(g.Genotype(a, b), g.Genotype(b, a))
        self.assertEqual(hash(g.Genotype(a, b)), hash(g.Genotype(b, a)))

    def test_objects_are_immutable(self):
        haplotype = g.reference_haplotype()
        with self.assertRaises(Exception):
            haplotype.alleles = ()                                   # type: ignore[misc]

    def test_an_allele_outside_the_alphabet_is_a_construction_error(self):
        with self.assertRaises(g.GenomeError):
            g.Haplotype((7,) + (0,) * 11)

    def test_length_stays_inside_the_bounded_band(self):
        with self.assertRaises(g.GenomeError):
            g.Haplotype((0,) * (g.MAX_LENGTH + 1))

    def test_operations_are_values_not_calls(self):
        """A specification has to be able to enumerate operations. That requires
        them to be comparable, hashable data."""
        self.assertEqual(ops.Substitute(3, 1), ops.Substitute(3, 1))
        self.assertEqual(len({ops.Substitute(3, 1), ops.Substitute(3, 1)}), 1)


# ------------------------------------------------ oracle layer 1: algebra ----
class TestAlleleConservation(unittest.TestCase):
    """A direct relation between parents and the products actually returned."""

    def test_reciprocal_crossover_conserves_every_allele(self):
        first = g.Haplotype((0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2))
        second = g.Haplotype((2, 1, 0, 2, 1, 0, 2, 1, 0, 2, 1, 0))
        for point in range(len(first) + 1):
            operation = ops.Recombine(point)
            children = ops.reciprocal(operation, first, second)
            self.assertEqual(
                orc.allele_conservation(operation, first, second, *children), "",
                f"crossover at {point} did not conserve alleles")

    def test_the_invariant_detects_a_lost_allele(self):
        """A conservation law nothing can violate proves nothing."""
        first = g.Haplotype((0,) * 12)
        second = g.Haplotype((2,) * 12)
        operation = ops.Recombine(6)
        child, _ = ops.reciprocal(operation, first, second)
        self.assertEqual(
            orc.allele_conservation(
                operation, first, second, child, child),
            "allele_not_conserved")

    def test_evaluate_checks_the_products_that_were_actually_executed(self):
        original = ops.reciprocal

        def broken(operation, first, second):
            child, _ = original(operation, first, second)
            return child, child

        ops.reciprocal = broken
        try:
            result = orc.evaluate(
                g.Genotype(g.Haplotype((0,) * 12), g.Haplotype((2,) * 12)),
                [ops.Recombine(6)])
            self.assertEqual(result.code, orc.VERDICT_ORACLE_DISAGREEMENT)
            self.assertEqual(result.reason, "allele_not_conserved")
        finally:
            ops.reciprocal = original


# ------------------------------------------- oracle layer 2: differential ----
class TestTraitEvaluatorsAgree(unittest.TestCase):
    def test_the_two_evaluators_agree_across_the_sampled_space(self):
        environments = [env.Environment(t, n, d)
                        for t in (0, 1, 2) for n in (0, 1) for d in (0, 1)]
        states = [(0, 0), (0, 2), (2, 2), (1, 2)]
        checked = 0
        for combo in itertools.product(states, repeat=4):
            genotype = _genotype(list(combo) + [(0, 0)] * 8)
            for environment in environments:
                value, _ = orc.trait_value(genotype, environment)
                self.assertEqual(value, orc.reference_trait_value(genotype, environment),
                                 f"{combo} in {environment}")
                checked += 1
        self.assertGreater(checked, 1000)

    def test_the_evaluators_are_not_the_same_code(self):
        """If they were factored together the differential layer would be a
        no-op. Cheap structural check that they remain two implementations."""
        source = (MODEL_DIR / "oracle.py").read_text(encoding="utf-8")
        body = source[source.index("def reference_trait_value"):]
        self.assertNotIn("trait_value(", body.split("def reference_trait_value")[1][:1200],
                         "the reference evaluator delegates to the model's own")

    def test_reference_evaluator_bypasses_the_evaluated_gxe_helper(self):
        """A shared helper defect must not make both evaluators agree wrongly."""
        genotype = g.homozygous_reference()
        original = orc.gxe_effect
        orc.gxe_effect = lambda locus, count, environment: 1
        try:
            observed, _ = orc.trait_value(genotype)
            expected = orc.reference_trait_value(genotype)
            self.assertNotEqual(observed, expected)
            result = orc.evaluate(genotype)
            self.assertEqual(result.code, orc.VERDICT_ORACLE_DISAGREEMENT)
            self.assertEqual(result.reason, "trait_differential_mismatch")
        finally:
            orc.gxe_effect = original


# ----------------------------------------------- what makes it interesting ---
class TestInteractionTermsAreReachableAndNonAdditive(unittest.TestCase):
    """If the interaction terms were unreachable or merely additive there would be
    nothing here that combinatorial construction finds and simpler analysis does
    not. This is the property the whole application exists to provide."""

    def _trait(self, operations, environment=None):
        return orc.trait_value(_apply_both(operations), environment)[0]

    def test_epistasis_is_reachable_and_beats_the_additive_prediction(self):
        base = self._trait([])
        only_1 = self._trait([ops.Substitute(1, 2)])
        only_3 = self._trait([ops.Substitute(3, 2)])
        both = self._trait([ops.Substitute(1, 2), ops.Substitute(3, 2)])
        additive_prediction = only_1 + only_3 - base
        self.assertNotEqual(both, additive_prediction)
        self.assertEqual(both - additive_prediction, 12)

    def test_environment_interaction_is_reachable(self):
        variant = [ops.Substitute(2, 2)]
        self.assertEqual(self._trait(variant, env.Environment(temperature=1)), 0)
        self.assertEqual(self._trait(variant, env.Environment(temperature=2)), 7)

    def test_a_suppressing_interaction_exists_too(self):
        """Not every interaction may point the same way, or a study could pass by
        always pushing the trait upward."""
        self.assertTrue(any(effect < 0 for effect in orc.EPISTATIC_EFFECTS.values()))


# ------------------------------------------- oracle layer 4: the contract ----
class TestTheViabilityContractCanActuallyFire(unittest.TestCase):
    """A contract that never fires is decoration. The second flagship SUT shipped
    with exactly that defect, so each reason gets a concrete witness here."""

    def test_the_upper_bound_is_reachable(self):
        genotype = _genotype([(2, 2)] * 4 + [(0, 0)] * 2 + [(2, 2)] * 2
                             + [(0, 0)] + [(2, 2)] + [(0, 0)] * 2)
        trait, _ = orc.trait_value(genotype, env.Environment(2, 1, 1))
        self.assertGreater(trait, orc.VIABLE_HIGH)
        self.assertEqual(orc.viability_violation(genotype, trait),
                         "trait_out_of_viable_range")

    def test_the_lower_bound_is_reachable(self):
        genotype = _genotype([(0, 0), (2, 2), (0, 0), (0, 0), (0, 2), (2, 2),
                              (2, 2), (0, 0), (0, 2), (0, 0), (2, 2), (0, 0)])
        trait, _ = orc.trait_value(genotype, env.Environment(1, 0, 0))
        self.assertLess(trait, orc.VIABLE_LOW)
        self.assertEqual(orc.viability_violation(genotype, trait),
                         "trait_out_of_viable_range")

    def test_an_unaligned_pair_is_a_contract_answer_not_a_crash(self):
        genotype = g.homozygous_reference()
        shortened = ops.apply(ops.Delete(0), genotype.left)
        self.assertEqual(orc.viability_violation(g.Genotype(shortened, genotype.right), 0),
                         "chromosomes_not_aligned")

    def test_unaligned_recombination_remains_a_contract_answer(self):
        """A crossover swaps unequal lengths; that is not an oracle defect."""
        genotype = g.Genotype(
            g.Haplotype((0,) * 12),
            g.Haplotype((2,) * 11))
        result = orc.evaluate(genotype, [ops.Recombine(5)])
        self.assertEqual(result.code, orc.VERDICT_CONTRACT)
        self.assertEqual(result.reason, "chromosomes_not_aligned")

    def test_the_reference_organism_is_viable(self):
        """The baseline must pass, or every candidate fails for a reason that has
        nothing to do with what is being varied."""
        self.assertEqual(orc.evaluate(g.homozygous_reference()).code, orc.VERDICT_PASS)


# ------------------------------------------------------- the whole verdict ---
class TestEvaluateClassifiesEveryOutcome(unittest.TestCase):
    def test_an_impossible_operation_is_a_construction_failure(self):
        result = orc.evaluate(g.homozygous_reference(), [ops.Substitute(99, 1)])
        self.assertEqual(result.code, orc.VERDICT_CONSTRUCTION)

    def test_an_indel_past_the_band_is_a_construction_failure(self):
        deletes = [ops.Delete(0)] * 6
        self.assertEqual(orc.evaluate(g.homozygous_reference(), deletes).code,
                         orc.VERDICT_CONSTRUCTION)

    def test_structural_bound_checks_the_executed_pair(self):
        """The non-executing length model must catch an operation-path defect."""
        original = orc.apply_pair

        def broken(operation, first, second):
            if isinstance(operation, ops.Substitute):
                return (g.Haplotype(first.alleles + (0,)),
                        g.Haplotype(second.alleles + (0,)))
            return original(operation, first, second)

        orc.apply_pair = broken
        try:
            result = orc.evaluate(
                g.homozygous_reference(), [ops.Substitute(0, 1)])
            self.assertEqual(result.code, orc.VERDICT_ORACLE_DISAGREEMENT)
            self.assertEqual(result.reason, "length_bound_exceeded")
        finally:
            orc.apply_pair = original

    def test_metrics_use_the_same_keys_as_the_engine_demonstrations(self):
        """One Analyzer configuration must serve all three domains when this model
        is later driven by a specification."""
        line = orc.evaluate(g.homozygous_reference(), [ops.Recombine(4)]).metrics_line()
        for key in ("stages", "depth", "branches", "ops", "retained", "reason", "FW_VAR"):
            self.assertIn(f"{key}=", line)

    def test_recombination_is_counted_as_a_branch(self):
        result = orc.evaluate(g.homozygous_reference(), [ops.Recombine(3), ops.Recombine(5)])
        self.assertEqual(result.branches, 2)
        self.assertEqual(result.depth, 3)

    def test_evaluation_is_deterministic(self):
        operations = [ops.Substitute(1, 2), ops.Recombine(6), ops.Substitute(3, 2)]
        first = orc.evaluate(g.homozygous_reference(), operations)
        second = orc.evaluate(g.homozygous_reference(), operations)
        self.assertEqual(first, second)


# ------------------------------------------------------------- the D7 seam ---
class TestTheExpertSeamStaysUnimplemented(unittest.TestCase):
    """D7 is undecided. These tests fail if somebody fills the seam in as a side
    effect of unrelated work — which is exactly what the notice in that module
    asks them not to do."""

    def test_no_expert_model_is_installed(self):
        self.assertFalse(expert_model.is_expert_model_available())
        with self.assertRaises(NotImplementedError):
            expert_model.load_expert_model()

    def test_no_expert_faults_are_installed(self):
        self.assertEqual(dict(expert_model.EXPERT_FAULTS), {})

    def test_the_seam_carries_the_owner_notice(self):
        """The notice is the reason this stub survives cleanup passes. If it is
        gone, so is the protection."""
        source = (HERE / "expert_model.py").read_text(encoding="utf-8")
        self.assertIn("for special user's request, separately against of any future fixes",
                      source)
        self.assertIn("D7 STUB -- DELIBERATELY NOT IMPLEMENTED", source)


if __name__ == "__main__":
    unittest.main()
