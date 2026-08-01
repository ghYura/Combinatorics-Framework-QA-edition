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
