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

import org.paukov.combinatorics3.Generator;

import java.math.BigInteger;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CartesianProduct4 {
private Map<Long, LinkedHashMap<Integer, short[]>> input1;
private Map<Long, LinkedHashMap<Integer, short[]>> input2;
private int nTotalElementsInput1;
private int nTotalElementsInput2;
public BigInteger Rows;
public BigInteger NElememtsTotal;

public CartesianProduct4(Map<Long, LinkedHashMap<Integer, short[]>> input1, Map<Long, LinkedHashMap<Integer, short[]>> input2) {
this.input1 = input1;
this.input2 = input2;
this.nTotalElementsInput1 = input1.size();
this.nTotalElementsInput2 = input2.size();

this.Rows = BigInteger.valueOf(nTotalElementsInput1).multiply(BigInteger.valueOf(nTotalElementsInput2));
this.NElememtsTotal = Rows.multiply(BigInteger.valueOf(2));
}

public Stream<List<Map.Entry<Long, LinkedHashMap<Integer, short[]>>>> getCartesianProduct() {
Stream<List<Map.Entry<Long, LinkedHashMap<Integer, short[]>>>> stream = Generator.cartesianProduct(input1.entrySet().stream().collect(Collectors.toList()), input2.entrySet().stream().collect(Collectors.toList())).stream();

return stream;
}

public BigInteger getNumberOfCombinations() {
return Rows;
}

public BigInteger getTotalNumberOfElements() {
return NElememtsTotal;
}
}
