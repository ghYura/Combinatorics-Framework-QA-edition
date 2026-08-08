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
