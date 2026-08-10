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
// Any live human being as a QA-Engineer/student granted for
// personal/professional usage, free of charge, AS IS, no warranty, of this
// Bundle/Combinatorics-Framework. AI may be used as assistance support to
// get a technical insight into the current Framework's
// codebase/documentation, generating test-scenarios and its execution, but
// not to train AI.
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.company.combinatorics;

import com.company.models.FW;
import org.paukov.combinatorics3.Generator;
import org.paukov.combinatorics3.IGenerator;
import org.ghYura.combinatorics3parallel.CombinatoricsUtils;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedList;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;


public class SubsetsG {
private int[] inpArr;
private boolean adviseDPaukov = true;
private Mode mode = Mode.DEFAULT;
private static boolean suppressEmptySubset = false;
private static boolean printSubsets = false;
private List<com.company.models.FW> input;
private int nTotalElementsInput;

public BigInteger Rows;
public BigInteger NElememtsTotal;

public SubsetsG(List<com.company.models.FW> input) {
this.input = input;
this.nTotalElementsInput = input.size();

inpArr = new int[input.size()];
for (int i = 1; i <= input.size(); i++) {
inpArr[i - 1] = i;
}
}

public SubsetsG(List<com.company.models.FW> input, Mode mode, boolean suppressEmptySubset) {
this.input = input;
this.nTotalElementsInput = input.size();

inpArr = new int[input.size()];
for (int i = 1; i <= input.size(); i++) {
inpArr[i - 1] = i;
}
this.setMode(mode);
SubsetsG.suppressEmptySubset = suppressEmptySubset;
}

public void calculateNumberOfCombinations() {
if (mode == Mode.DEFAULT) {
this.Rows = BigInteger.valueOf(2).pow(input.size());
this.NElememtsTotal = coef(nTotalElementsInput);
return;
}



long count = 0;
int  n     = input.size();
for (int sz = 0; sz <= n; sz++) {
boolean match;
switch (mode) {
case BEFORE: match = suppressEmptySubset ? (sz > 0 && sz < inpArr[0]) : (sz < inpArr[0]); break;
case AFTER:  match = sz > inpArr[0]; break;
case EXACT:  match = sz == inpArr[0]; break;
case RANGE:  match = sz >= inpArr[0] && sz <= inpArr[1]; break;
case GIVEN:
match = false;
for (int v : inpArr) { if (v == sz) { match = true; break; } }
break;
default: match = false; break;
}
if (match) count += CombinatoricsUtils.binomial(n, sz);
}
this.Rows = BigInteger.valueOf(count);
if (printSubsets) System.out.println();
}

public Stream getDistinctCombinations() {
return getDistinctCombinations(inpArr);
}

public Stream getDistinctCombinations(int... inp) {
this.setInpArr(inp);
int n = input.size();

if (mode == Mode.DEFAULT) {
return adviseDPaukov
? Generator.subset(input).simple().stream()
: new org.ghYura.combinatorics3parallel.SubSetGenerator<>(input).stream();
}



List<Integer> targetSizes = new ArrayList<>();
for (int sz = 0; sz <= n; sz++) {
boolean match;
switch (mode) {
case BEFORE: match = suppressEmptySubset ? (sz > 0 && sz < inp[0]) : (sz < inp[0]); break;
case AFTER:  match = sz > inp[0]; break;
case EXACT:  match = sz == inp[0]; break;
case RANGE:  match = sz >= inp[0] && sz <= inp[1]; break;
case GIVEN:
match = false;
for (int v : inp) { if (v == sz) { match = true; break; } }
break;
default: match = false; break;
}
if (match) targetSizes.add(sz);
}

if (adviseDPaukov) {
return targetSizes.stream()
.map(sz -> Generator.combination(input).simple(sz))
.flatMap(IGenerator::stream);
}
return targetSizes.stream()
.map(sz -> new org.ghYura.combinatorics3parallel.CombinationGenerator<>(input, sz))
.flatMap(org.ghYura.combinatorics3parallel.IGenerator::stream);
}

public BigInteger getNumberOfCombinations() {
calculateNumberOfCombinations();
return Rows;
}

public BigInteger getTotalNumberOfElements() {
return NElememtsTotal;
}

private BigInteger factorialBig(int f) {
BigInteger result = BigInteger.ONE;
for (int i = 2; i <= f; i++) {
result = result.multiply(BigInteger.valueOf(i));
}
return result;
}

private BigInteger coef(int nTotalElementsInput) {
int curNumber = 0;
int nTotalElementsInputLocal = nTotalElementsInput;
int totalNumbers = nTotalElementsInput + 1;
BigInteger sum = BigInteger.ZERO;
BigInteger curCoef;

while (curNumber < totalNumbers) {
curCoef = factorialBig(nTotalElementsInput)
.divide(factorialBig(curNumber).multiply(factorialBig(nTotalElementsInput - curNumber)));
sum = sum.add(curCoef.multiply(BigInteger.valueOf(nTotalElementsInputLocal)));
nTotalElementsInputLocal--;
curNumber++;
}
return sum;
}


private static <T> Stream orderedSubSets(T[] arr, int start, int end) {
assert (start >= 0);
assert (end <= arr.length);
return IntStream.rangeClosed(start, end)
.mapToObj(i -> Generator.combination(arr).simple(i).stream());
}

private static <T> Stream givenSubSets(T[] arr, int... given) {
return IntStream.of(given)
.mapToObj(i -> Generator.combination(arr).simple(i).stream());
}

private static Stream orderedSubSets(List<FW> list, int start, int end) {
assert (start >= 0);
assert (end <= list.size());
IntStream intStream = IntStream.rangeClosed(start, end);
List<IGenerator<List<FW>>> lst = new LinkedList<>();
intStream.forEach(i -> lst.add(Generator.combination(list).simple(i)));
return lst.stream().flatMap(e -> e.stream());
}

private static Stream givenSubSets(List<FW> list, int... given) {
IntStream intStream = IntStream.of(given);
List<IGenerator<List<FW>>> lst = new LinkedList<>();
intStream.forEach(i -> lst.add(Generator.combination(list).simple(i)));
return lst.stream().flatMap(e -> e.stream());
}

public Mode getMode() { return mode; }

public void setMode(Mode mode) { this.mode = mode; }

public int[] getInpArr() { return inpArr; }

public void setInpArr(int[] inpArr) { this.inpArr = inpArr; }

public enum Mode {
DEFAULT, BEFORE, AFTER, EXACT, RANGE, GIVEN
}


public Stream getDistinctCombinationsDP(int... inp) {
return getDistinctCombinations(inp);
}
}
