package com.company.bundle;

import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Tier-3.5 — pluggable strategy contract for the closed-loop XLSX/JSON
 * mutation step.  Given a parsed-workbook JSON tree (the root
 * {@code { sheets: { name: [[cells...]...] } }} object) and a
 * {@link BundleSeedAdapter} carrying the previous iteration's winners,
 * a strategy edits the tree in-place to produce the next iteration's
 * schedule.
 *
 * <p>The orchestrator (out of scope here) wires this:</p>
 *
 * <pre>
 *   workbook_iter{N}.json + bundle_seed.json
 *           ↓ WorkbookMutator.mutateJsonFile(..., strategy)
 *           ↓ strategy.mutate(workbookRoot, seed)
 *   workbook_iter{N+1}.json
 *           ↓ Core re-launched with excel.file=workbook_iter{N+1}.json
 * </pre>
 *
 * <p>Why operate on raw JSON, not on {@link com.company.excel.ParsedWorkbook}?
 * The orchestrator path must stay POI-free (Jackson is enough; POI dragging
 * in XSSF / xmlbeans / commons-compress would bloat the orchestrator JVM and
 * defeat the "JSON is lightweight" rationale of Tier-3.5).  Strategies that
 * need access to ParsedWorkbook for harder transformations can call
 * {@code JsonScheduleParser.parseJson(...)} themselves — they just opt in to
 * the heavier path.</p>
 *
 * <p><strong>Two-axis catalogue</strong>:</p>
 * <ol>
 *   <li><strong>Option B / structural-only</strong> ({@link ElitismStrategy},
 *       {@link NoopStrategy}) — adds / removes / re-orders sheets and rows
 *       without parsing cell content.  Universal: works for any cell semantic
 *       (code fragments, regex, DSL).</li>
 *   <li><strong>Option A / cell-introspection</strong> (future
 *       {@code CellIntrospectionStrategy}) — parses cell text for embedded
 *       numeric markers (e.g. {@code cost=NUM}, {@code int latency = NUM;})
 *       and narrows ranges around seed winners.  Only works on schedules
 *       whose authors follow a marker convention.</li>
 * </ol>
 *
 * <p>Implementations should be:</p>
 * <ul>
 *   <li>Stateless and thread-safe (so the orchestrator can re-use a single
 *       instance across iterations).</li>
 *   <li>Idempotent — running the same strategy twice on the same input
 *       should produce the same output (or no further changes).</li>
 *   <li>Additive — preserve all existing sheets / rows / cells unless the
 *       strategy's documented contract explicitly says otherwise.</li>
 * </ul>
 */
public interface WorkbookMutationStrategy {

    /**
     * Mutate {@code workbookRoot} in-place using {@code seed}.
     *
     * @param workbookRoot top-level JSON node of the schedule (the
     *                      {@code { sheets: { ... } }} object).  Mutate
     *                      sub-trees directly; the orchestrator will write
     *                      the result back to disk.
     * @param seed         the previous iteration's BundleSeed (winners,
     *                      observedRanges, declaredMetrics).  May be empty
     *                      if no winners survived; strategy must handle.
     * @return short human-readable summary suitable for logging
     *         (e.g. {@code "Elitism: added 12 FW_Seed_* sheets from 12 winners"}).
     */
    String mutate(ObjectNode workbookRoot, BundleSeedAdapter seed);

    /** Short name for logging / strategy-by-property selection. */
    String name();
}
