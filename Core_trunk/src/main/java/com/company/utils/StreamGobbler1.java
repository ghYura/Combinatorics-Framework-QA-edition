package com.company.utils;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.util.function.Consumer;

public class StreamGobbler1 implements Runnable {
private InputStream inputStream;
private Consumer<String> consumer;

public StreamGobbler1(InputStream inputStream, Consumer<String> consumer) {
this.inputStream = inputStream;
this.consumer = consumer;
}

@Override
public void run() {
new BufferedReader(new InputStreamReader(inputStream)).lines()
.forEach(consumer);
}
}
