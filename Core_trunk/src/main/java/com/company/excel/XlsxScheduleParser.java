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
 * Legacy XLSX schedule parser — thin wrapper over {@link WorkbookParser}.
 * Preserves byte-for-byte the historical behaviour of the engine when
 * fed an {@code .xlsx} file.
 */
public final class XlsxScheduleParser implements ScheduleParser {
    @Override
    public ParsedWorkbook parse(Path source, AppConfig.WorkbookConfig wbCfg) throws Exception {
        return WorkbookParser.parse(source, wbCfg);
    }
}
