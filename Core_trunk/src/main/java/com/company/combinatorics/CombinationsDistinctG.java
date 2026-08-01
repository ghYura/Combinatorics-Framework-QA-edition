package com.company.combinatorics;

import org.ghYura.combinatorics3parallel.CombinationGenerator;
import org.paukov.combinatorics3.Generator;

import java.math.BigInteger;
import java.util.List;
import java.util.stream.Stream;


public class CombinationsDistinctG {

private List input;
private int nTotalElementsInput;
private int mElementsPerRowOutput;
private boolean adviseDPaukov = true;
public BigInteger Rows;
public BigInteger NElememtsTotal;

public CombinationsDistinctG(List input, int mElementsPerRowOutput) {
this(input, mElementsPerRowOutput, true);
}

public CombinationsDistinctG(List input, int mElementsPerRowOutput, boolean adviseDPaukov) {
this.input = input;
this.nTotalElementsInput = input.size();
this.mElementsPerRowOutput = mElementsPerRowOutput;
this.adviseDPaukov = adviseDPaukov;

if (mElementsPerRowOutput < 0 || mElementsPerRowOutput > nTotalElementsInput) {
this.Rows = BigInteger.ZERO;
} else {
this.Rows = binomial(nTotalElementsInput, mElementsPerRowOutput);
}
this.NElememtsTotal = Rows.multiply(BigInteger.valueOf(Math.max(0, mElementsPerRowOutput)));
}

public Stream getDistinctCombinations() {
if (adviseDPaukov) {
return Generator.combination(input).simple(mElementsPerRowOutput).stream();
}
return new CombinationGenerator<>(input, mElementsPerRowOutput).stream();
}

public BigInteger getNumberOfCombinations() { return Rows; }

public BigInteger getTotalNumberOfElements() { return NElememtsTotal; }


private static BigInteger binomial(int n, int k) {
if (k < 0 || k > n) return BigInteger.ZERO;
if (k == 0 || k == n) return BigInteger.ONE;
if (k > n - k) k = n - k;
BigInteger res = BigInteger.ONE;
for (int i = 1; i <= k; i++) {
res = res.multiply(BigInteger.valueOf(n - i + 1))
.divide(BigInteger.valueOf(i));
}
return res;
}
}
