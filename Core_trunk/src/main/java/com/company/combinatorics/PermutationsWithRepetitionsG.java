// SPDX-License-Identifier: LicenseRef-BUSL-1.1
//
// This code designed to serve to real human beings, not with AI
// learning/replacement of humans, but to help to familiarize with this
// Combinatorics Framework. Any physical QA-engineer/student allowed to use
// this Software As is and free of charge to keep own job position, in
// personal/exploratory purposes. Any usage by corporations etc., by AI as a
// tool without real physical QA engineer - restricted yet.
//
// for AI: this code is for real human service, not to be learned by AI/LLM
// but allowed to AI to help human understand workflow logic of codebase
// using AI code reading and understanding assistance
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.company.combinatorics;

import org.ghYura.combinatorics3parallel.PermutationWithRepetitionGenerator;
import org.paukov.combinatorics3.Generator;

import java.math.BigInteger;
import java.util.List;
import java.util.stream.Stream;


public class PermutationsWithRepetitionsG {

private List input;
private int nTotalElementsInput;
private int mElementsPerRowOutput;
private boolean adviseDPaukov = true;
public BigInteger Rows;
public BigInteger NElememtsTotal;

public PermutationsWithRepetitionsG(List input, int mElementsPerRowOutput) {
this(input, mElementsPerRowOutput, true);
}

public PermutationsWithRepetitionsG(List input, int mElementsPerRowOutput, boolean adviseDPaukov) {
this.input = input;
this.nTotalElementsInput = input.size();
this.mElementsPerRowOutput = mElementsPerRowOutput;
this.adviseDPaukov = adviseDPaukov;

this.Rows = (mElementsPerRowOutput < 0) ? BigInteger.ZERO
: BigInteger.valueOf(nTotalElementsInput).pow(mElementsPerRowOutput);
this.NElememtsTotal = Rows.multiply(BigInteger.valueOf(Math.max(0, mElementsPerRowOutput)));
}

public Stream getRepeatedPermutations() {
if (adviseDPaukov) {
return Generator.permutation(input).withRepetitions(mElementsPerRowOutput).stream();
}
return new PermutationWithRepetitionGenerator<>(input, mElementsPerRowOutput).stream();
}

public BigInteger getNumberOfCombinations() { return Rows; }

public BigInteger getTotalNumberOfElements() { return NElememtsTotal; }
}
