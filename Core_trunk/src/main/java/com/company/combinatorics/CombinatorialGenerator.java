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


import org.ghYura.combinatorics3parallel.CombinationGenerator;
import org.ghYura.combinatorics3parallel.MultiCombinationGenerator;
import org.ghYura.combinatorics3parallel.PermutationGenerator;
import org.ghYura.combinatorics3parallel.MultiPermutationGenerator;
import org.ghYura.combinatorics3parallel.PermutationWithRepetitionGenerator;
import org.ghYura.combinatorics3parallel.SubSetGenerator;
import org.ghYura.combinatorics3parallel.CartesianProductGenerator;


import org.paukov.combinatorics3.Generator;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;


public final class CombinatorialGenerator<T> {




public enum SubsetMode {
DEFAULT, BEFORE, AFTER, EXACT, RANGE, GIVEN
}




private final List<org.paukov.combinatorics3.IGenerator<List<T>>> seqDelegates;


private final List<org.ghYura.combinatorics3parallel.IGenerator<List<T>>> parDelegates;


public final boolean parallel;




public final BigInteger rowCount;


public final BigInteger totalElements;



private CombinatorialGenerator(
List<org.paukov.combinatorics3.IGenerator<List<T>>> seqDelegates,
List<org.ghYura.combinatorics3parallel.IGenerator<List<T>>> parDelegates,
boolean parallel,
BigInteger rowCount,
BigInteger totalElements) {
this.seqDelegates  = seqDelegates;
this.parDelegates  = parDelegates;
this.parallel      = parallel;
this.rowCount      = rowCount;
this.totalElements = totalElements;
}




public static <T> CombinatorialGenerator<T> combinations(
List<T> input, int r, boolean parallel) {
int        n       = input.size();
BigInteger rows    = binom(n, r);
BigInteger totalEl = rows.multiply(BigInteger.valueOf(r));
if (parallel) {
return new CombinatorialGenerator<>(
null,
List.of(new CombinationGenerator<>(input, r)),
true, rows, totalEl);
} else {
return new CombinatorialGenerator<>(
List.of(Generator.combination(input).simple(r)),
null,
false, rows, totalEl);
}
}


public static <T> CombinatorialGenerator<T> combinationsWithRepetitions(
List<T> input, int r, boolean parallel) {
int        n       = input.size();
BigInteger rows    = binom(n + r - 1, r);
BigInteger totalEl = rows.multiply(BigInteger.valueOf(r));
if (parallel) {
return new CombinatorialGenerator<>(
null,
List.of(new MultiCombinationGenerator<>(input, r)),
true, rows, totalEl);
} else {
return new CombinatorialGenerator<>(
List.of(Generator.combination(input).multi(r)),
null,
false, rows, totalEl);
}
}


public static <T> CombinatorialGenerator<T> permutations(
List<T> input, boolean treatDuplicatesAsIdentical, boolean parallel) {
int n = input.size();
if (treatDuplicatesAsIdentical) {
var        counter = new MultiPermutationGenerator<>(input);
long       count   = counter.getNumberOfGeneratedElements();
BigInteger rows    = BigInteger.valueOf(count);
BigInteger totalEl = rows.multiply(BigInteger.valueOf(n));
// [Iter4.1 fix] Use ghYura's MultiPermutationGenerator as the delegate for
// BOTH parallel and sequential paths.  dpaukov 3.3.3's
// Generator.permutation(input).simple(TreatDuplicatesAs.IDENTICAL) does
// NOT actually dedup multisets — it streams all n! permutations regardless
// of the IDENTICAL flag.  Verified by CombinatorialRowCountVerify:
// for input [1,1,2,3] dpaukov yields 24 rows while rowCount (via ghYura
// counter above) reports the correct 12.  That mismatch silently broke
// the precompute-rowCount contract for the entire treatDup=true sequential
// path.  Routing the sequential path through ghYura makes count + stream
// agree.  parallelStreams() handles the parallel=false case by falling
// through to a single-thread stream — no chunked parallelism, correct semantics.
return new CombinatorialGenerator<>(null, List.of(counter), parallel, rows, totalEl);
} else {
BigInteger rows    = factorial(n);
BigInteger totalEl = rows.multiply(BigInteger.valueOf(n));
if (parallel) {
return new CombinatorialGenerator<>(
null,
List.of(new PermutationGenerator<>(input)),
true, rows, totalEl);
} else {
return new CombinatorialGenerator<>(
List.of(Generator.permutation(input).simple()),
null,
false, rows, totalEl);
}
}
}


public static <T> CombinatorialGenerator<T> permutationsWithRepetitions(
List<T> input, int r, boolean parallel) {
int        n       = input.size();
BigInteger rows    = BigInteger.valueOf(n).pow(r);
BigInteger totalEl = rows.multiply(BigInteger.valueOf(r));
if (parallel) {
return new CombinatorialGenerator<>(
null,
List.of(new PermutationWithRepetitionGenerator<>(input, r)),
true, rows, totalEl);
} else {
return new CombinatorialGenerator<>(
List.of(Generator.permutation(input).withRepetitions(r)),
null,
false, rows, totalEl);
}
}


public static <T> CombinatorialGenerator<T> cartesian(
List<T> a, List<T> b, boolean parallel) {
BigInteger rows    = BigInteger.valueOf((long) a.size() * b.size());
BigInteger totalEl = rows.multiply(BigInteger.TWO);
if (parallel) {
return new CombinatorialGenerator<>(
null,
List.of(new CartesianProductGenerator<>(List.of(a, b))),
true, rows, totalEl);
} else {
return new CombinatorialGenerator<>(
List.of(Generator.cartesianProduct(a, b)),
null,
false, rows, totalEl);
}
}


public static <T> CombinatorialGenerator<T> cartesianProduct(
List<List<T>> lists, boolean parallel) {
var        gen     = new CartesianProductGenerator<>(lists);
BigInteger rows    = BigInteger.valueOf(gen.getNumberOfGeneratedElements());
BigInteger totalEl = rows.multiply(BigInteger.valueOf(lists.size()));
return new CombinatorialGenerator<>(null, List.of(gen), parallel, rows, totalEl);
}


public static <T> CombinatorialGenerator<T> subsets(
List<T> input, SubsetMode mode, int[] params, boolean parallel) {
int n = input.size();


if (mode == SubsetMode.DEFAULT || params.length == 0) {
BigInteger rows    = BigInteger.TWO.pow(n);
BigInteger totalEl = (n == 0)
? BigInteger.ZERO
: BigInteger.valueOf(n).multiply(BigInteger.TWO.pow(n - 1));
if (parallel) {
return new CombinatorialGenerator<>(
null,
List.of(new SubSetGenerator<>(input)),
true, rows, totalEl);
} else {
return new CombinatorialGenerator<>(
List.of(Generator.subset(input).simple()),
null,
false, rows, totalEl);
}
}


final int[] p = params;
List<Integer> targetSizes = new ArrayList<>();
for (int sz = 0; sz <= n; sz++) {
boolean match = switch (mode) {
case BEFORE -> sz < p[0];
case AFTER  -> sz > p[0];
case EXACT  -> sz == p[0];
case RANGE  -> sz >= p[0] && sz <= p[1];
case GIVEN  -> {
boolean found = false;
for (int pv : p) if (pv == sz) { found = true; break; }
yield found;
}
default     -> true;
};
if (match) targetSizes.add(sz);
}

BigInteger rows    = BigInteger.ZERO;
BigInteger totalEl = BigInteger.ZERO;

List<org.paukov.combinatorics3.IGenerator<List<T>>>          seqList = new ArrayList<>();
List<org.ghYura.combinatorics3parallel.IGenerator<List<T>>>  parList = new ArrayList<>();

for (int sz : targetSizes) {
BigInteger cRows = binom(n, sz);
rows    = rows.add(cRows);
totalEl = totalEl.add(cRows.multiply(BigInteger.valueOf(sz)));

if (parallel) {
parList.add(new CombinationGenerator<>(input, sz));
} else {
seqList.add(Generator.combination(input).simple(sz));
}
}

return new CombinatorialGenerator<>(
parallel ? null : seqList,
parallel ? parList : null,
parallel, rows, totalEl);
}




public Stream<List<T>> stream() {
if (parallel && parDelegates != null) {
return parDelegates.stream()
.flatMap(org.ghYura.combinatorics3parallel.IGenerator::stream);
}
if (seqDelegates != null) {
return seqDelegates.stream()
.flatMap(org.paukov.combinatorics3.IGenerator::stream);
}
if (parDelegates != null) {

return parDelegates.stream()
.flatMap(org.ghYura.combinatorics3parallel.IGenerator::stream);
}
return Stream.empty();
}


public List<Stream<List<T>>> parallelStreams(int threads) {
if (parallel && parDelegates != null && !parDelegates.isEmpty()) {
if (parDelegates.size() == 1) {
return parDelegates.get(0).asArrayOfStreamsForGivenThreads(threads);
}




long totalCount = rowCount.bitLength() > 62
? Long.MAX_VALUE
: rowCount.longValueExact();
if (totalCount <= 0) return Collections.emptyList();

List<Stream<List<T>>> result = new ArrayList<>();
int  threadsRemaining = threads;
long countRemaining   = totalCount;

for (int i = 0; i < parDelegates.size(); i++) {
var  delegate = parDelegates.get(i);
long delCount = delegate.getNumberOfGeneratedElements();
if (delCount == 0) continue;

int delThreads;
if (i == parDelegates.size() - 1) {
delThreads = Math.max(1, threadsRemaining);
} else {
delThreads = (int) Math.round(
(double) delCount / countRemaining * threadsRemaining);
if (delThreads < 1) delThreads = 1;
if (delThreads > threadsRemaining) delThreads = Math.max(1, threadsRemaining);
}

result.addAll(delegate.asArrayOfStreamsForGivenThreads(delThreads));
threadsRemaining -= delThreads;
countRemaining   -= delCount;
if (threadsRemaining < 1) threadsRemaining = 1;
}
return result;
}
return List.of(stream());
}



private static BigInteger factorial(int n) {
BigInteger r = BigInteger.ONE;
for (int i = 2; i <= n; i++) r = r.multiply(BigInteger.valueOf(i));
return r;
}

private static BigInteger binom(int n, int r) {
if (r < 0 || r > n) return BigInteger.ZERO;
return factorial(n).divide(factorial(r).multiply(factorial(n - r)));
}
}
