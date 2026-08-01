package com.company.combinatorics;

import org.ghYura.combinatorics3parallel.MultiPermutationGenerator;
import org.paukov.combinatorics3.Generator;
import org.paukov.combinatorics3.PermutationGenerator;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;


public class PermutationsSimpleG {

private boolean allowDuplicate = false;
private boolean adviseDPaukov = true;
private List input;
public BigInteger Rows;
public BigInteger NElememtsTotal;

public PermutationsSimpleG(List input, boolean allowDuplicate) {
this(input, allowDuplicate, true);
}

public PermutationsSimpleG(List input, boolean allowDuplicate, boolean adviseDPaukov) {
this.allowDuplicate = allowDuplicate;
this.adviseDPaukov  = adviseDPaukov;
this.input          = input;
int n = input.size();

if (allowDuplicate) {

this.Rows = factorialBig(n);
} else {

this.Rows = multisetPermutationCount(input);
}
this.NElememtsTotal = Rows.multiply(BigInteger.valueOf(n));
}

public Stream getPermutationsSimple() {
if (adviseDPaukov) {
return allowDuplicate
? Generator.permutation(input).simple(PermutationGenerator.TreatDuplicatesAs.IDENTICAL).stream()
: Generator.permutation(input).simple().stream();
}



if (allowDuplicate) {
return Generator.permutation(input).simple(PermutationGenerator.TreatDuplicatesAs.IDENTICAL).stream();
}
return new MultiPermutationGenerator<>(input).stream();
}

public BigInteger getNumberOfCombinations() { return Rows; }

public BigInteger getTotalNumberOfElements() { return NElememtsTotal; }

private static BigInteger factorialBig(int f) {
BigInteger result = BigInteger.ONE;
for (int i = 2; i <= f; i++) result = result.multiply(BigInteger.valueOf(i));
return result;
}


private static BigInteger multisetPermutationCount(List items) {
int n = items.size();
if (n == 0) return BigInteger.ONE;
Map<Object, Integer> counts = new HashMap<>();
for (Object o : items) counts.merge(o, 1, Integer::sum);
BigInteger res = factorialBig(n);
for (int c : counts.values()) res = res.divide(factorialBig(c));
return res;
}
}
