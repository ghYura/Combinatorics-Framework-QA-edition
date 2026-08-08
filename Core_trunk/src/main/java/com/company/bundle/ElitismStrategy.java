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

package com.company.bundle;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Tier-3.5 Option B MVP — structural elitism via FW_Seed_* sheet injection.
 *
 * <p>For every winner in the BundleSeed, append a new sheet named
 * {@code FW_Seed_<lineNo>_<role>} to the workbook JSON, containing one row
 * whose single cell is the winner's K=V representation
 * ({@code "cost=0.10 latency=9.0 throughput=4500"}).  These survive into
 * Iter-{N+1}'s combinatorial pool — winners "live" through to the next
 * generation, no cell-content parsing required, no risk of breaking the
 * original schedule.</p>
 *
 * <p>The orchestrator (or the human author of {@code FW_Seq}) decides how to
 * wire the new sheets into the combinatorial recipe; this strategy stays
 * intentionally minimal and additive.  Two natural follow-up strategies that
 * could build on top:</p>
 * <ul>
 *   <li>{@code FwSeqAppendingElitism} — also adds matching rows to
 *       {@code FW_Seq} ({@code [FW_Seed_<id>, FW_Exclude, FW_Reuse,
 *       FW_Combi(1), FW_Combi(1)]}) so the seed sheets participate
 *       automatically.</li>
 *   <li>{@code CellIntrospectionStrategy} — Tier-3.5 Option A, parses cell
 *       text for embedded numeric markers and narrows ranges around the
 *       winners' values.</li>
 * </ul>
 *
 * <p><strong>Configuration:</strong></p>
 * <ul>
 *   <li>{@code sheetNamePrefix} — defaults to {@code "FW_Seed_"}. Used in
 *       sheet names to make them visually distinct from human-authored sheets.</li>
 *   <li>{@code rolePrefixFilter} — when non-empty, only winners whose role
 *       starts with this prefix are injected.  Use {@code "pareto"} to keep
 *       only Pareto-front members; {@code "balanced:"} to keep only
 *       scalarization picks.  Null/empty → all winners injected.</li>
 *   <li>{@code includeRoleInName} — when {@code true} (default), sheet name
 *       is {@code FW_Seed_<lineNo>_<sanitisedRole>}.  When {@code false},
 *       just {@code FW_Seed_<lineNo>} (collisions on multi-role winners
 *       are skipped via the idempotent guard).</li>
 * </ul>
 *
 * <p>Idempotent: if a sheet with the derived name already exists in the
 * workbook, this strategy skips it.  Re-running the same strategy on its own
 * output produces no additional changes.</p>
 */
public final class ElitismStrategy implements WorkbookMutationStrategy {

    /** Default sheet-name prefix.  Intentionally does NOT start with {@code FW_}
     *  — Core's {@code WorkbookParser} reserves the {@code FW_} prefix for a
     *  fixed control-sheet whitelist ({@code FW_Seq}, {@code FW_SheetNames},
     *  {@code FW_RunMeFirstOnce}, etc.) and silently drops any other FW_-prefixed
     *  sheet during routing.  {@code Seed_} keeps the elitism sheets in the
     *  data-sheet space ({@code shortSheetHM}) so they're usable downstream
     *  as combinatorial inputs. */
    private static final String DEFAULT_PREFIX = "Seed_";

    private final String  sheetNamePrefix;
    private final String  rolePrefixFilter;
    private final boolean includeRoleInName;

    /** Default: prefix {@code FW_Seed_}, all roles, role-suffixed names. */
    public ElitismStrategy() {
        this(DEFAULT_PREFIX, null, true);
    }

    public ElitismStrategy(String sheetNamePrefix,
                            String rolePrefixFilter,
                            boolean includeRoleInName) {
        this.sheetNamePrefix    = (sheetNamePrefix == null || sheetNamePrefix.isBlank())
                                    ? DEFAULT_PREFIX : sheetNamePrefix;
        this.rolePrefixFilter   = (rolePrefixFilter == null || rolePrefixFilter.isBlank())
                                    ? null : rolePrefixFilter;
        this.includeRoleInName  = includeRoleInName;
    }

    @Override
    public String mutate(ObjectNode workbookRoot, BundleSeedAdapter seed) {
        if (workbookRoot == null) {
            throw new IllegalArgumentException("workbookRoot must be non-null");
        }
        if (seed == null || seed.winnerCount() == 0) {
            return "Elitism: no winners in seed (added 0 sheets)";
        }

        // Ensure 'sheets' sub-object exists.
        JsonNode sheetsRaw = workbookRoot.path("sheets");
        ObjectNode sheets;
        if (sheetsRaw.isObject()) {
            sheets = (ObjectNode) sheetsRaw;
        } else {
            sheets = workbookRoot.putObject("sheets");
        }

        Set<String> existing = new LinkedHashSet<>();
        sheets.fieldNames().forEachRemaining(existing::add);

        int added = 0;
        int skippedExisting = 0;
        int filteredOut = 0;
        for (BundleSeedAdapter.Winner w : seed.winners) {
            if (rolePrefixFilter != null && !w.role.startsWith(rolePrefixFilter)) {
                filteredOut++;
                continue;
            }
            String rowText = encodeKvAsRow(w.kvPairs);
            if (rowText.isEmpty()) continue;

            String sheetName = sheetNamePrefix + w.lineNo
                    + (includeRoleInName ? "_" + sanitiseRole(w.role) : "");
            if (existing.contains(sheetName)) { skippedExisting++; continue; }

            ArrayNode rows = sheets.putArray(sheetName);
            ArrayNode cells = rows.addArray();
            cells.add(rowText);
            existing.add(sheetName);
            added++;
        }

        return String.format(Locale.ROOT,
                "Elitism: added %d %s* sheets (filtered out %d by role-prefix '%s', "
                + "skipped %d already-present) from %d total winners",
                added, sheetNamePrefix, filteredOut,
                rolePrefixFilter == null ? "" : rolePrefixFilter,
                skippedExisting, seed.winnerCount());
    }

    @Override
    public String name() { return "Elitism"; }

    /** Format the winner's K=V map as a single space-separated row, matching
     *  the convention the Reader emits when streaming combinatorial rows
     *  (so downstream LineParser.KvLineParser ingests them identically). */
    private static String encodeKvAsRow(Map<String, String> kvPairs) {
        if (kvPairs == null || kvPairs.isEmpty()) return "";
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        for (Map.Entry<String, String> e : kvPairs.entrySet()) {
            if (!first) sb.append(' ');
            sb.append(e.getKey()).append('=').append(e.getValue() == null ? "" : e.getValue());
            first = false;
        }
        return sb.toString();
    }

    /** Sheet names must be valid POI sheet identifiers — strip anything
     *  non-alphanumeric (the BundleSeed role can contain ':' and ',' for
     *  champion / balanced labels). */
    private static String sanitiseRole(String role) {
        if (role == null || role.isEmpty()) return "x";
        return role.replaceAll("[^A-Za-z0-9]", "_");
    }
}
