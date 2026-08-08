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

package com.company.excel;

import com.company.config.AppConfig;

import java.nio.file.Path;

/**
 * Format-agnostic input adapter for the Combinatorics engine.  The engine
 * downstream of this point ({@code SeqParser}, {@code SheetWorker}, etc.)
 * works exclusively against {@link ParsedWorkbook} — which is itself a
 * Builder around POI {@code Sheet} objects.  Implementations of this
 * interface accept whatever serialised form (XLSX, JSON, YAML, …) and
 * return that {@link ParsedWorkbook}.
 *
 * Mirror of the {@code com.yurii.analyzer.core.optimization.LineParser}
 * pattern on the Analyzer side: same architectural rationale — keep the
 * canonical model (here {@code ParsedWorkbook}; there
 * {@code Map<String,String> kvPairs}) and plug in arbitrary input
 * adapters around it.
 *
 * Implementations are stateless and thread-safe.
 *
 * Two built-in impls:
 *   • {@link XlsxScheduleParser} — current XLSX behaviour (delegates to
 *     {@link WorkbookParser#parse})
 *   • {@link JsonScheduleParser} — JSON file → in-memory POI workbook →
 *     same downstream pipeline
 */
public interface ScheduleParser {

    /**
     * @param source  path to the input file (or URI / inline content depending
     *                on the impl; XLSX/JSON impls expect a filesystem path)
     * @param wbCfg   workbook config (auto-generate-missing-sheets flags etc.)
     * @return        the parsed canonical model
     */
    ParsedWorkbook parse(Path source, AppConfig.WorkbookConfig wbCfg) throws Exception;

    /**
     * Pick an impl by file extension.  {@code .xlsx} / {@code .xlsm} →
     * {@link XlsxScheduleParser}; {@code .json} → {@link JsonScheduleParser};
     * {@code .yaml} / {@code .yml} → {@link YamlScheduleParser};
     * {@code .toml} → {@link TomlScheduleParser};
     * otherwise defaults to XLSX (the legacy behaviour).
     */
    static ScheduleParser forFile(Path source) {
        String name = source.getFileName().toString().toLowerCase(java.util.Locale.ROOT);
        if (name.endsWith(".json"))                       return new JsonScheduleParser();
        if (name.endsWith(".yaml") || name.endsWith(".yml")) return new YamlScheduleParser();
        if (name.endsWith(".toml"))                       return new TomlScheduleParser();
        return new XlsxScheduleParser();
    }

    /** Explicit by-name resolver — used when {@code core.input.format} is set.
     *
     *  Note: {@code "programmatic"} / {@code "java"} cannot be resolved here
     *  because there is no schedule source file to read.  See
     *  {@link ProgrammaticScheduleBuilder#asScheduleParser()} to plug a
     *  pre-built fluent schedule into this shelf at runtime. */
    static ScheduleParser byName(String formatName) {
        if (formatName == null) return new XlsxScheduleParser();
        switch (formatName.trim().toLowerCase(java.util.Locale.ROOT)) {
            case "json": return new JsonScheduleParser();
            case "yaml", "yml": return new YamlScheduleParser();
            case "toml": return new TomlScheduleParser();
            case "xlsx":
            case "xlsm":
            default:     return new XlsxScheduleParser();
        }
    }
}
