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

package com.company.utils;

import java.util.concurrent.ForkJoinPool;


public final class ThreadPoolUtil {

private ThreadPoolUtil() { }


public static ForkJoinPool newPool(int parallelism) {
if (parallelism < 1) throw new IllegalArgumentException("parallelism must be >= 1");
return new ForkJoinPool(parallelism);
}


public static ForkJoinPool newDefaultPool() {
return new ForkJoinPool(Runtime.getRuntime().availableProcessors());
}




@Deprecated
public static int foo(int i, int j) {
return 0;
}


@Deprecated
public static float foo(float i, float j) {
return 0f;
}
}
