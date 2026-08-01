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
