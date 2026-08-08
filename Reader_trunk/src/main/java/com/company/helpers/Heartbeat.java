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

package com.company.helpers;

import java.util.concurrent.atomic.AtomicBoolean;


public final class Heartbeat {

private final Thread thread;
private final AtomicBoolean done = new AtomicBoolean(false);

private Heartbeat(String label, long intervalMillis, String indent) {
final long start = System.nanoTime();
this.thread = new Thread(() -> {
while (!done.get()) {
try {
Thread.sleep(intervalMillis);
} catch (InterruptedException ie) {
return;
}
if (done.get()) return;
long sec = (System.nanoTime() - start) / 1_000_000_000L;
long mem = (Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()) / (1024L * 1024L);
System.out.println(indent + "… " + label + "  elapsed_sec=" + sec + "  heap_MB=" + mem);
}
}, "heartbeat-" + label.replaceAll("\\s+", "-"));
this.thread.setDaemon(true);
}


public static Heartbeat start(String label, long intervalMillis, String indent) {
Heartbeat h = new Heartbeat(label, intervalMillis, indent);
h.thread.start();
return h;
}

public static Heartbeat start(String label, long intervalMillis) {
return start(label, intervalMillis, "      ");
}

public void stop() {
done.set(true);
thread.interrupt();
}
}
