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

package com.yurii.analyzer.core.parallel;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

/**
 * Per-worker-queue scheduler with tag-affinity routing.
 *
 * Each worker registers a {@link java.util.Set} of capability tags it can
 * handle.  Each task is given a tag by a {@link LineTagger} on submission;
 * the scheduler picks the least-loaded worker whose capability set contains
 * the task's tag.  If no eligible worker exists (or the tag is empty/null),
 * the task falls back to least-loaded across ALL workers — preserving liveness
 * even when callers misconfigure tags.
 *
 * Typical use: dedicate workers to specific runtimes (e.g. {@code python},
 * {@code shell}, {@code jvm}) so the executor doesn't pay per-task startup
 * cost.  Or pin GPU-bound work to a single worker and let CPU work spread.
 *
 * Construction:
 * <pre>{@code
 * Map<Integer, Set<String>> caps = Map.of(
 *     0, Set.of("python"),
 *     1, Set.of("python"),
 *     2, Set.of("shell", "jvm"),
 *     3, Set.of("shell", "jvm"));
 * LineTagger tagger = (lineNo, raw) ->
 *     raw.startsWith("python ") ? "python" :
 *     raw.startsWith("./") || raw.startsWith("/bin/") ? "shell" : "jvm";
 * Scheduler s = new CapabilityAwareScheduler(4, caps, tagger);
 * }</pre>
 */
public final class CapabilityAwareScheduler implements Scheduler {

    private final int parallelism;
    private final BlockingQueue<Task>[] queues;
    private final LineTagger tagger;
    private final Map<String, int[]> tagToWorkers;        // index → worker ids
    private final int[] allWorkers;                       // fallback list

    public CapabilityAwareScheduler(int parallelism,
                                    Map<Integer, Set<String>> workerCapabilities,
                                    LineTagger tagger) {
        this(parallelism, workerCapabilities, tagger, 256);
    }

    @SuppressWarnings("unchecked")
    public CapabilityAwareScheduler(int parallelism,
                                    Map<Integer, Set<String>> workerCapabilities,
                                    LineTagger tagger,
                                    int perWorkerCapacity) {
        if (parallelism <= 0) throw new IllegalArgumentException("parallelism must be > 0");
        if (perWorkerCapacity <= 0) throw new IllegalArgumentException("perWorkerCapacity must be > 0");
        this.parallelism = parallelism;
        this.tagger = Objects.requireNonNullElse(tagger, LineTagger.NONE);

        this.queues = (BlockingQueue<Task>[]) new BlockingQueue[parallelism];
        for (int i = 0; i < parallelism; i++) {
            // +1 slot to guarantee close() never blocks publishing POISON.
            queues[i] = new ArrayBlockingQueue<>(perWorkerCapacity + 1);
        }

        // Invert worker → tags into tag → workers, validate worker ids.
        Map<String, List<Integer>> inv = new HashMap<>();
        Map<Integer, Set<String>> caps = (workerCapabilities == null) ? Map.of() : workerCapabilities;
        for (Map.Entry<Integer, Set<String>> e : caps.entrySet()) {
            int wid = e.getKey();
            if (wid < 0 || wid >= parallelism)
                throw new IllegalArgumentException("worker id out of range: " + wid);
            for (String t : (e.getValue() == null ? Set.<String>of() : e.getValue())) {
                if (t == null || t.isEmpty()) continue;
                inv.computeIfAbsent(t, k -> new ArrayList<>()).add(wid);
            }
        }
        this.tagToWorkers = new HashMap<>();
        for (Map.Entry<String, List<Integer>> e : inv.entrySet()) {
            int[] arr = e.getValue().stream().mapToInt(Integer::intValue).distinct().toArray();
            this.tagToWorkers.put(e.getKey(), arr);
        }
        this.allWorkers = new int[parallelism];
        for (int i = 0; i < parallelism; i++) allWorkers[i] = i;
    }

    @Override public void submit(int lineNo, String raw) throws InterruptedException {
        String tag = tagger.tag(lineNo, raw);
        int[] eligible = (tag == null || tag.isEmpty()) ? allWorkers
                : tagToWorkers.getOrDefault(tag, allWorkers);
        int chosen = pickLeastLoaded(eligible);
        queues[chosen].put(new Task(lineNo, raw));
    }

    @Override public Task take(int workerId) throws InterruptedException {
        return queues[workerId].take();
    }

    @Override public void close() throws InterruptedException {
        for (int i = 0; i < parallelism; i++) queues[i].put(Task.POISON);
    }

    public int[] pendingCounts() {
        int[] out = new int[parallelism];
        for (int i = 0; i < parallelism; i++) out[i] = queues[i].size();
        return out;
    }

    /** Read-only view of the inverted tag map.  Useful for diagnostics. */
    public Map<String, int[]> tagToWorkersView() {
        return Collections.unmodifiableMap(tagToWorkers);
    }

    private int pickLeastLoaded(int[] eligible) {
        int best = eligible[0];
        int bestSize = queues[best].size();
        for (int i = 1; i < eligible.length; i++) {
            int w = eligible[i];
            int s = queues[w].size();
            if (s < bestSize) { bestSize = s; best = w; }
        }
        return best;
    }

    // Visible for tests: returns workers eligible for a given tag, in input order.
    Set<Integer> eligibleWorkersFor(String tag) {
        int[] arr = (tag == null || tag.isEmpty()) ? allWorkers
                : tagToWorkers.getOrDefault(tag, allWorkers);
        Set<Integer> s = new HashSet<>(arr.length * 2);
        for (int w : arr) s.add(w);
        return s;
    }
}
