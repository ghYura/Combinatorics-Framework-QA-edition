// SPDX-License-Identifier: LicenseRef-BUSL-1.1
// (c) Yurii Baranov, Kyiv, Ukraine. See LICENSE and NOTICE.md for binding terms.
// AI assistance supports a real human QA engineer; no AI training is authorized.

package com.company.excel;

import com.company.SheetWorker;
import com.company.config.AppConfig;
import com.company.keys.KeyCodec;
import com.company.keys.KeyCodecs;
import com.company.store.IntermediateTableStore;
import com.company.store.JavaIntermediateTableStore;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;

/** Deterministic workflow regressions using the real worker and in-memory store, for both
 * key widths. No DB, candidate execution, or external files are needed.
 * Run: java -cp Core_trunk/target/migrated-project-1.0-SNAPSHOT.jar
 * com.company.excel.SheetWorkerWorkflowVerify
 */
public final class SheetWorkerWorkflowVerify {
    private static int failures;

    private SheetWorkerWorkflowVerify() {}

    public static void main(String[] args) throws Exception {
        for (KeyCodec<?> codec : List.of(KeyCodecs.SHORT, KeyCodecs.BYTE)) run(codec);
        if (failures != 0) throw new AssertionError(failures + " WORKFLOW CHECK(S) FAILED");
        System.out.println("ALL SHEET-WORKER WORKFLOW CHECKS PASSED");
    }

    private static <A> void run(KeyCodec<A> codec) throws Exception {
        System.out.println("-- " + codec.arrayClass().getSimpleName() + " --");
        ParsedWorkbook wb = workbook();
        short key = wb.stringShortSheetName2SheetKeyHM.get("G");
        for (String method : List.of("appendFwRow", "createFw2Table", "swapFw2ToFw")) {
            JavaIntermediateTableStore<A> store = new JavaIntermediateTableStore<>(codec);
            IntermediateTableStore<A> broken = failingStore(store, method);
            List<String> program = List.of("FW_Combi(1)", "FW_Combi(size)", "FW_Combi(size)");
            Throwable failure = failureOf(() -> process(wb, config(Map.of()), broken, key, program));
            check(method + " failure aborts processing and preserves its cause",
                    hasMessage(failure, "injected " + method));
        }

        for (Map.Entry<String, Map<String, String>> policy : Map.of(
                "authoring", Map.of("core.replace.patternPolicy", "strict"),
                "unmatched", Map.of("core.replace.unmatchedPolicy", "fail"),
                "unparseable", Map.of("core.replace.unparseablePolicy", "fail")).entrySet()) {
            String pattern = policy.getKey().equals("unparseable") ? "\\d+" : "NO_MATCH";
            String group = "FW_Group\nFW_ReplaceRE(\"" + pattern + "\", \"bad\")";
            Throwable failure = failureOf(() -> process(wb, config(policy.getValue()),
                    new JavaIntermediateTableStore<>(codec), key,
                    List.of("FW_Combi(1)", group, "FW_Combi(1)")));
            check(policy.getKey() + " fail policy rejects the run", failure != null);
        }

        Throwable badRegex = failureOf(() -> process(wb, config(Map.of()),
                new JavaIntermediateTableStore<>(codec), key,
                List.of("FW_Combi(1)", "FW_Group\nFW_ReplaceRE(\"[\", \"4\")", "FW_Combi(1)")));
        check("invalid rewrite regex aborts the run", hasMessage(badRegex, "Unclosed character class"));

        // Submit the dependent brace first: it must wait for the operand even when
        // that operand has not been submitted yet, and must reject its partial rows.
        JavaIntermediateTableStore<A> dependencyStore = new JavaIntermediateTableStore<>(codec);
        for (short k : wb.sheetData.keySet()) dependencyStore.createFwTable(k);
        SheetWorker<A> dependencyWorker = new SheetWorker<>(config(Map.of()), null, null, wb, dependencyStore);
        short joinKey = wb.stringShortSheetName2SheetKeyHM.get("J");
        short other = wb.stringShortSheetName2SheetKeyHM.get("B1");
        Map<Short, List<Short>> source = new LinkedHashMap<>();
        source.put(joinKey, wb.sheetData.get(joinKey));
        source.put(other, wb.sheetData.get(other));
        source.put(key, wb.sheetData.get(key));
        Throwable dependencyFailure = failureOf(() -> dependencyWorker.processAll(source,
                new ConcurrentHashMap<>(), new ConcurrentHashMap<>(), Map.of(
                        joinKey, List.of("FW_(,,G,,B1,,,,M:N)"),
                        other, List.of("FW_Combi(1)", "FW_Combi(size)"),
                        key, List.of("FW_Combi(1)", "FW_Group\nFW_ReplaceRE(\"[\", \"4\")",
                                "FW_Combi(1)")), Set.of(key, other), Set.of(), List.of(), List.of()));
        check("brace refuses a failed operand's partial rows",
                dependencyFailure != null && dependencyStore.count(joinKey, true) == 0
                        && !dependencyWorker.getKey2tableMap().containsKey(joinKey));

        JavaIntermediateTableStore<A> plain = new JavaIntermediateTableStore<>(codec);
        SheetWorker<A> worker = process(wb, config(Map.of()), plain, key,
                List.of("FW_Combi(1)", "FW_Combi(size)"));
        check("ordinary per-row program retains both source rows", plain.count(key, true) == 2);
        check("ordinary completed sheet is registered", worker.getKey2tableMap().containsKey(key));

        JavaIntermediateTableStore<A> empty = new JavaIntermediateTableStore<>(codec);
        worker = process(wb, config(Map.of()), empty, key,
                List.of("FW_Combi(1)", "FW_Combi(2)", "FW_Combi(1)"));
        check("intentional empty result remains nonfatal and unregistered",
                !worker.getKey2tableMap().containsKey(key) && empty.count(key, true) == 0);

        groupedCartes(wb, codec, key, false, false);
        groupedCartes(wb, codec, key, true, false);
        groupedCartes(wb, codec, key, false, true);
        groupedCartes(wb, codec, key, true, true);

        // FW_Group follows a completed per-row pass here. A stale audit claimed the
        // sub-combination route skipped the rewrite: pin its actual supported behavior.
        JavaIntermediateTableStore<A> laterGroup = new JavaIntermediateTableStore<>(codec);
        String originalCode = Short.toString(wb.sheetData.get(key).get(0));
        short replacement = wb.sheetData.get(wb.stringShortSheetName2SheetKeyHM.get("B2")).get(0);
        process(wb, config(Map.of()), laterGroup, key, List.of("FW_Combi(1)", "FW_Combi(size)",
                "FW_Group\nFW_ReplaceRE(\"" + originalCode + "\", \"" + replacement + "\")",
                "FW_Combi(1)"));
        Set<List<Integer>> expected = Set.of(List.of((int) replacement),
                List.of((int) wb.sheetData.get(key).get(1)));
        check("group after per-row pass applies its rewrite", rows(laterGroup, codec, key).equals(expected));
    }

    private static <A> void groupedCartes(ParsedWorkbook wb, KeyCodec<A> codec, short key,
                                          boolean first, boolean injectSeparator) throws Exception {
        JavaIntermediateTableStore<A> store = new JavaIntermediateTableStore<>(codec);
        String verb = first ? "FW_Cartes_first" : "FW_Cartes";
        String group = "FW_Group";
        if (injectSeparator) group += "\nFW_ReplaceRE(\"(?<=\\d)\\, \", \", \" + S1 + \", \")";
        process(wb, config(Map.of()), store, key,
                List.of(verb + "(B1)", group, verb + "(B2)"));
        List<Short> g = wb.sheetData.get(key);
        List<Short> b1 = wb.sheetData.get(wb.stringShortSheetName2SheetKeyHM.get("B1"));
        List<Short> b2 = wb.sheetData.get(wb.stringShortSheetName2SheetKeyHM.get("B2"));
        short separator = wb.sheetData.get(wb.stringShortSheetName2SheetKeyHM.get("S1")).get(0);
        Set<List<Integer>> expected = new TreeSet<>((a, b) -> a.toString().compareTo(b.toString()));
        for (short n : g) for (short asc : b1) for (short up : b2) {
            List<Integer> row = new ArrayList<>();
            if (first) {
                row.add((int) up);
                if (injectSeparator) row.add((int) separator);
                row.add((int) asc);
                if (injectSeparator) row.add((int) separator);
                row.add((int) n);
            } else {
                row.add((int) n);
                if (injectSeparator) row.add((int) separator);
                row.add((int) asc);
                row.add((int) up);
            }
            expected.add(row);
        }
        Set<List<Integer>> actual = rows(store, codec, key);
        check(verb + (injectSeparator ? " with code-boundary rewrite" : " without rewrite")
                + " preserves all eight authored rows", actual.equals(expected));
        if (!actual.equals(expected)) System.out.println("  expected=" + expected + " actual=" + actual);
    }

    private static ParsedWorkbook workbook() {
        ParsedWorkbook.Builder b = new ParsedWorkbook.Builder();
        short key = 0;
        short code = 10;
        for (String name : List.of("G", "B1", "B2", "S1", "J")) {
            key++;
            b.key2name.put(key, name);
            b.name2key.put(name, key);
            b.sheetData.put(key, name.equals("S1") ? List.of(code++) : List.of(code++, code++));
        }
        b.maxSheetNumber = key;
        return b.build();
    }

    private static <A> SheetWorker<A> process(ParsedWorkbook wb, AppConfig cfg,
                                              IntermediateTableStore<A> store, short key,
                                              List<String> program) throws Exception {
        for (short k : wb.sheetData.keySet()) store.createFwTable(k);
        SheetWorker<A> worker = new SheetWorker<>(cfg, null, null, wb, store);
        Map<Short, List<Short>> source = new ConcurrentHashMap<>(wb.sheetData);
        worker.processAll(source, new ConcurrentHashMap<>(), new ConcurrentHashMap<>(),
                Map.of(key, program));
        return worker;
    }

    @SuppressWarnings("unchecked")
    private static <A> IntermediateTableStore<A> failingStore(IntermediateTableStore<A> delegate,
                                                              String failingMethod) {
        return (IntermediateTableStore<A>) Proxy.newProxyInstance(
                IntermediateTableStore.class.getClassLoader(), new Class<?>[]{IntermediateTableStore.class},
                (proxy, method, args) -> {
                    if (method.getName().equals(failingMethod)) {
                        if (failingMethod.equals("appendFwRow"))
                            throw new IllegalStateException("injected " + failingMethod);
                        throw new SQLException("injected " + failingMethod);
                    }
                    try { return method.invoke(delegate, args); }
                    catch (InvocationTargetException e) { throw e.getCause(); }
                });
    }

    private static <A> Set<List<Integer>> rows(IntermediateTableStore<A> store, KeyCodec<A> codec,
                                                short key) {
        Set<List<Integer>> rows = new TreeSet<>((a, b) -> a.toString().compareTo(b.toString()));
        for (A combo : store.readFw2Combos(key)) {
            List<Integer> row = new ArrayList<>();
            for (int n : codec.toInts(combo)) row.add(n);
            rows.add(row);
        }
        return rows;
    }

    private static AppConfig config(Map<String, String> edits) throws Exception {
        Properties p = new Properties();
        p.putAll(Map.of("db.user", "unused", "db.password", "unused", "db.host", "127.0.0.1",
                "db.name", "unused", "db.port", "5433", "excel.file", "unused.xlsx"));
        p.setProperty("core.limitVarGivenLessThan", "1000");
        p.setProperty("core.counter4copyMax", "100");
        for (String name : List.of("core.sleepTimeAfterDisconnect4copyDB", "core.sleepTimeCheckFinalFilled",
                "core.optional.limitOptionalSheetsCombosMax",
                "core.optional.numberOptionalSheetCombosMultithreadStartsAfter",
                "delay_holdCleanupAndEraseExcludedTablesThread", "delay_holdMockupPreparationOfSqlFinalTableThread",
                "delay_holdFnlThread", "delay_holdOptsThread")) p.setProperty(name, "0");
        p.setProperty("distinctify__fwX_Y__Tables", "true");
        p.putAll(edits);
        Path props = Files.createTempFile("core-workflow-verify-", ".properties");
        try {
            try (var out = Files.newOutputStream(props)) { p.store(out, "No database is used"); }
            return AppConfig.load(props);
        } finally { Files.deleteIfExists(props); }
    }

    private interface CheckedRunnable { void run() throws Exception; }

    private static Throwable failureOf(CheckedRunnable action) {
        try { action.run(); return null; }
        catch (Throwable failure) { return failure; }
    }

    private static boolean hasMessage(Throwable error, String part) {
        for (Throwable t = error; t != null; t = t.getCause())
            if (t.getMessage() != null && t.getMessage().contains(part)) return true;
        return false;
    }

    private static void check(String label, boolean ok) {
        System.out.println((ok ? "PASS " : "FAIL ") + label);
        if (!ok) failures++;
    }
}
