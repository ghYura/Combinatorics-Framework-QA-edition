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
