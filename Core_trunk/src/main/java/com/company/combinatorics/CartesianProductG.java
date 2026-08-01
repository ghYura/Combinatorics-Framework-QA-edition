package com.company.combinatorics;

import org.ghYura.combinatorics3parallel.CartesianProductGenerator;
import org.paukov.combinatorics3.Generator;

import java.math.BigInteger;
import java.util.List;
import java.util.stream.Stream;


public class CartesianProductG {

private List input1;
private List input2;
private int nTotalElementsInput1;
private int nTotalElementsInput2;
private boolean adviseDPaukov = true;
public BigInteger Rows;
public BigInteger NElememtsTotal;

public CartesianProductG(List input1, List input2) {
this(input1, input2, true);
}

public CartesianProductG(List input1, List input2, boolean adviseDPaukov) {
this.input1 = input1;
this.input2 = input2;
this.nTotalElementsInput1 = input1.size();
this.nTotalElementsInput2 = input2.size();
this.adviseDPaukov = adviseDPaukov;
this.Rows = BigInteger.valueOf(nTotalElementsInput1)
.multiply(BigInteger.valueOf(nTotalElementsInput2));
this.NElememtsTotal = Rows.multiply(BigInteger.valueOf(2));
}

public Stream getCartesianProduct() {





if (adviseDPaukov) {
return Generator.cartesianProduct(input1, input2).stream();
}


@SuppressWarnings({"unchecked", "rawtypes"})
List<List<Object>> lists = (List) List.of(input1, input2);
return new CartesianProductGenerator<>(lists).stream();
}

public BigInteger getNumberOfCombinations() { return Rows; }

public BigInteger getTotalNumberOfElements() { return NElememtsTotal; }
}
