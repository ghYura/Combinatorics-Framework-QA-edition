package com.company;

import static com.company.Main.*;
import static com.company.ReaderConfig.*;
import com.company.helpers.QueryToDB;
import java.io.*;
import java.sql.*;
import java.util.*;

// Extracted from the Main god-class 2026-05-30 (behaviour-preserving Extract-Class).
/** SRP: write the Reader->Executor handshake artifacts the Executor consumes:
 *  runmefirstonce.first, args, and fwVar.shift (P6: never empty). */
public final class HandshakeWriter {
    private HandshakeWriter() {}

    public static void writeArgsRunOnceShift(QueryToDB q2drunFirstOnce_args)
            throws java.io.IOException, java.sql.SQLException {
        StringBuilder sbArgs = new StringBuilder();
FileWriter myWriterRunFirstOnce = new FileWriter(cfg().pathFwResultsFirstRunOnceResults());
myWriterRunFirstOnce.write(q2drunFirstOnce_args.queryForStr("SELECT code_once FROM public.runmefirstonce;"));
myWriterRunFirstOnce.close();
System.out.println("Successfully wrote RunFirstOnce to the file " + cfg().pathFwResultsFirstRunOnceResults());
q2drunFirstOnce_args.init();
FileWriter myWriterArgs = new FileWriter(cfg().pathFwResultsArgumentsResults());
ResultSet rsArgs = q2drunFirstOnce_args.queryForWholeResSet("SELECT * FROM public.arguments order by id;");
while (rsArgs.next()) {
sbArgs.append(" ").append(rsArgs.getString("args"));
}
myWriterArgs.write(sbArgs.toString());
myWriterArgs.close();
System.out.println("Successfully wrote Arguments to the file " + cfg().pathFwResultsArgumentsResults());

q2drunFirstOnce_args.init();
FileWriter myWriterFwVarShift = new FileWriter(cfg().pathFwResultsArgumentsResults().replaceFirst("((?<=/)[^\\/]+$)|((?<=\\\\)[^\\\\/]+$)", "fwVar.shift"));
// ── [Bundle-bred refactor 2026-05-30 — unit P6 HandshakeWriter] ──────────────────────────
// Never emit an EMPTY fwVar.shift. Originally this file was written ONLY in
// onlyFW_EXIT_CODEcolumns mode; otherwise it was left empty → the Executor's positional FW_VAR
// encoding underflows/overflows the INSERT (the documented "write 1 into fwVar.shift yourself"
// gotcha). The bred + verified winner (4/4) always writes a valid shift; default to "1" so a
// failing FW_VAR=k binds a combos column in range (k − shift, with shift=1 keeping k≥1 valid).
if (cfg().dbFwExitCodeColumnsOnlyResults())
myWriterFwVarShift.write(q2drunFirstOnce_args.queryForStr("SELECT MIN(fw_exit_code) FROM public.\"ColumnsContainFwExitCode\";"));
else
myWriterFwVarShift.write("1");
myWriterFwVarShift.close();
System.out.println("Successfully wrote fwVar.shift to the file " + cfg().pathFwResultsFirstRunOnceResults().replaceFirst("((?<=/)[^\\/]+$)|((?<=\\\\)[^\\\\/]+$)", "fwVar.shift"));

    }
}
