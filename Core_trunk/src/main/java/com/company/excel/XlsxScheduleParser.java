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
