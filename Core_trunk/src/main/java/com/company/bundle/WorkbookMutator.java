package com.company.bundle;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Tier-3.5 — orchestrator-side utility that closes the Master-mode loop.
 * Reads {@code workbook_iter{N}.json} (produced by Core's auto-dump) + the
 * Analyzer's {@code bundle_seed.json}, applies a
 * {@link WorkbookMutationStrategy}, writes {@code workbook_iter{N+1}.json}
 * to disk in a form the next Core iteration can directly consume via
 * {@code core.input.format=json}.
 *
 * <p>The mutator is intentionally framework-light: no POI, no Hibernate, no
 * c3p0 — just Jackson.  This keeps the orchestrator binary small and lets
 * the loop run on minimal hosts (CI runners, edge nodes, lightweight VMs).</p>
 *
 * <p>Typical orchestrator invocation:</p>
 * <pre>
 *   WorkbookMutator.mutateJsonFile(
 *       Path.of("workbook_iter2.json"),     // input from previous Core dump
 *       Path.of("bundle_seed.json"),         // input from previous Analyzer
 *       Path.of("workbook_iter3.json"),      // output for next Core
 *       new ElitismStrategy());
 * </pre>
 *
 * <p>Then re-launches Core with {@code excel.file=workbook_iter3.json} and
 * {@code core.input.format=json}; Core reads the JSON, auto-dumps
 * {@code workbook_iter3.iter0.json} (which is the same file effectively;
 * the {@code .iter0} suffix preserves the Iter-0 convention regardless of
 * which JSON the orchestrator hands in).</p>
 */
public final class WorkbookMutator {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private WorkbookMutator() {}

    /**
     * Read {@code inputJson}, apply {@code strategy} using
     * {@code seedJson}, write the mutated tree to {@code outputJson}
     * as pretty-printed JSON.
     *
     * <p>Auto-creates the parent of {@code outputJson} when missing.
     * Idempotent strategies + the same input pair → identical output bytes.</p>
     *
     * @return the strategy's summary string (already logged-friendly)
     * @throws IOException on read / parse / write failure
     * @throws IllegalArgumentException on missing inputs or invalid JSON
     *                                   schema (no top-level {@code sheets})
     */
    public static String mutateJsonFile(Path inputJson,
                                        Path seedJson,
                                        Path outputJson,
                                        WorkbookMutationStrategy strategy) throws IOException {
        if (inputJson == null || seedJson == null || outputJson == null)
            throw new IllegalArgumentException("inputJson, seedJson, outputJson must all be non-null");
        if (strategy == null) strategy = new NoopStrategy();
        if (!Files.isRegularFile(inputJson))
            throw new IllegalArgumentException("inputJson not found: " + inputJson);
        if (!Files.isRegularFile(seedJson))
            throw new IllegalArgumentException("seedJson not found: " + seedJson);

        String workbookText = Files.readString(inputJson, StandardCharsets.UTF_8);
        JsonNode rawRoot = MAPPER.readTree(workbookText);
        if (!(rawRoot instanceof ObjectNode)) {
            throw new IllegalArgumentException(
                    "inputJson is not an object: " + inputJson + " (root type: "
                            + (rawRoot == null ? "null" : rawRoot.getNodeType()) + ")");
        }
        ObjectNode root = (ObjectNode) rawRoot;

        BundleSeedAdapter seed = BundleSeedAdapter.loadFromFile(seedJson);

        String summary = strategy.mutate(root, seed);

        // Provenance — orchestrator-friendly metadata.  Skipped if a strategy
        // chose not to keep state (Noop) since the summary already says so.
        ObjectNode meta = root.with("_bundleMeta");
        meta.put("lastMutationStrategy", strategy.name());
        meta.put("lastMutationSummary",  summary);
        meta.put("lastMutationAtEpochMs", System.currentTimeMillis());
        meta.put("seedSourceRunId",      seed.sourceRunId);
        meta.put("seedWinnerCount",      seed.winnerCount());

        if (outputJson.getParent() != null) Files.createDirectories(outputJson.getParent());
        String json = MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(root);
        Files.writeString(outputJson, json, StandardCharsets.UTF_8);
        return summary;
    }

    /** In-memory variant: pass the JSON tree directly.  Useful for tests
     *  and for orchestrators that already hold the parsed tree in memory. */
    public static String mutateInMemory(ObjectNode workbookRoot,
                                         BundleSeedAdapter seed,
                                         WorkbookMutationStrategy strategy) {
        if (strategy == null) strategy = new NoopStrategy();
        return strategy.mutate(workbookRoot, seed);
    }
}
