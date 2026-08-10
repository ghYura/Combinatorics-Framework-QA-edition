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

package com.company;

import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class LoggerConsoleToSmartConsolePrinterBridge {
private static final PrintStream ORIGINAL_OUT = System.out;
private static final PrintStream ORIGINAL_ERR = System.err;

private static volatile boolean installed = false;

private LoggerConsoleToSmartConsolePrinterBridge() {}

public static synchronized void install() {
if (installed) {
return;
}


try {
Class.forName(SmartConsolePrinter.class.getName(), true,
SmartConsolePrinter.class.getClassLoader());
} catch (ClassNotFoundException e) {
throw new IllegalStateException("Cannot initialize SmartConsolePrinter", e);
}

System.setOut(new PrintStream(new RoutedOutputStream(false), true, StandardCharsets.UTF_8));
System.setErr(new PrintStream(new RoutedOutputStream(true), true, StandardCharsets.UTF_8));

installed = true;
}

public static synchronized void uninstall() {
if (!installed) {
return;
}
System.setOut(ORIGINAL_OUT);
System.setErr(ORIGINAL_ERR);
installed = false;
}

private static final class RoutedOutputStream extends OutputStream {
private final boolean err;
private final StringBuilder pending = new StringBuilder(256);

private RoutedOutputStream(boolean err) {
this.err = err;
}

@Override
public synchronized void write(int b) {
pending.append((char) (b & 0xFF));
drainCompleteLines(false);
}

@Override
public synchronized void write(byte[] b, int off, int len) {
pending.append(new String(b, off, len, StandardCharsets.UTF_8));
drainCompleteLines(false);
}

@Override
public synchronized void flush() {
drainCompleteLines(true);
}

@Override
public synchronized void close() {
drainCompleteLines(true);
}

private void drainCompleteLines(boolean flushRemainder) {
int start = 0;

for (int i = 0; i < pending.length(); i++) {
char c = pending.charAt(i);
if (c == '\n' || c == '\r') {
emitLine(pending.substring(start, i));

if (c == '\r' && i + 1 < pending.length() && pending.charAt(i + 1) == '\n') {
i++;
}
start = i + 1;
}
}

if (flushRemainder && start < pending.length()) {
emitPartial(pending.substring(start));
start = pending.length();
}

if (start > 0) {
pending.delete(0, start);
}
}

private void emitLine(String line) {
if (err) {
SmartConsolePrinter.errln(line);
} else {
SmartConsolePrinter.outln(line);
}
}

private void emitPartial(String text) {
if (text.isEmpty()) {
return;
}
if (err) {
SmartConsolePrinter.err(text);
} else {
SmartConsolePrinter.out(text);
}
}
}
}
