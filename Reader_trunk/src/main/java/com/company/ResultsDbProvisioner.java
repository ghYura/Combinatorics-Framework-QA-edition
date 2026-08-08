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

package com.company;

import static com.company.Main.*;
import static com.company.ReaderConfig.*;
import com.company.helpers.*;
import java.io.*;
import java.sql.*;
import java.util.*;

// Extracted from the Main god-class 2026-05-30 (behaviour-preserving Extract-Class).
/** SRP: provision the Results DB + table (DDL from describe_table, P5 alignment) and write the
 *  resultsDbURL.properties + insert.sql handshake. Reads Main's public static config via static import. */
public final class ResultsDbProvisioner {
    private ResultsDbProvisioner() {}

/**
 * Reduce {@code file} to owner-only access, best effort.
 *
 * Used for the handshake file that carries the results-database password. Never
 * fatal: a filesystem that cannot represent POSIX permissions (or a JDK that
 * declines) must not fail the run, it simply does not gain the extra protection.
 */
private static void restrictToOwner(File file) {
    try {
        java.nio.file.Files.setPosixFilePermissions(
                file.toPath(),
                java.nio.file.attribute.PosixFilePermissions.fromString("rw-------"));
    } catch (IOException | UnsupportedOperationException | SecurityException e) {
        // Fall back to the platform-independent API; still better than 0644.
        boolean ignored = file.setReadable(false, false) && file.setReadable(true, true);
    }
}

public static void create(String DB_HOST_results, int DB_PORT_results, String DB_USER_results, String DB_PASSWORD_results) {
System.out.print("createResultDBandTable() at work.\n DB RESULTS creation: ...\n");
QueryToDB q2d0 = new QueryToDB();
q2d0.init();
String sqlCreateFunction = """
CREATE OR REPLACE FUNCTION public.describe_table(p_schema_name character varying, p_table_name character varying)
  RETURNS SETOF text AS
$BODY$
DECLARE
    v_table_ddl   text;
    column_record record;
    table_rec record;
    constraint_rec record;
    firstrec boolean;
BEGIN
    FOR table_rec IN
        SELECT c.relname, c.oid FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE relkind = 'r'
                AND n.nspname = p_schema_name
                AND relname~ ('^('||p_table_name||')$')
          ORDER BY c.relname
    LOOP
        FOR column_record IN
            SELECT
                b.nspname as schema_name,
                b.relname as table_name,
                a.attname as column_name,
                pg_catalog.format_type(a.atttypid, a.atttypmod) as column_type,
                CASE WHEN
                    (SELECT substring(pg_catalog.pg_get_expr(d.adbin, d.adrelid) for 128)
                     FROM pg_catalog.pg_attrdef d
                     WHERE d.adrelid = a.attrelid AND d.adnum = a.attnum AND a.atthasdef) IS NOT NULL THEN
                    'DEFAULT '|| (SELECT substring(pg_catalog.pg_get_expr(d.adbin, d.adrelid) for 128)
                                  FROM pg_catalog.pg_attrdef d
                                  WHERE d.adrelid = a.attrelid AND d.adnum = a.attnum AND a.atthasdef)
                ELSE
                    ''
                END as column_default_value,
                CASE WHEN a.attnotnull = true THEN
                    'NOT NULL'
                ELSE
                    'NULL'
                END as column_not_null,
                a.attnum as attnum,
                e.max_attnum as max_attnum
            FROM
                pg_catalog.pg_attribute a
                INNER JOIN
                 (SELECT c.oid,
                    n.nspname,
                    c.relname
                  FROM pg_catalog.pg_class c
                       LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                  WHERE c.oid = table_rec.oid
                  ORDER BY 2, 3) b
                ON a.attrelid = b.oid
                INNER JOIN
                 (SELECT
                      a.attrelid,
                      max(a.attnum) as max_attnum
                  FROM pg_catalog.pg_attribute a
                  WHERE a.attnum > 0
                    AND NOT a.attisdropped
                  GROUP BY a.attrelid) e
                ON a.attrelid=e.attrelid
            WHERE a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
        LOOP
            IF column_record.attnum = 1 THEN
                v_table_ddl:='CREATE UNLOGGED TABLE IF NOT EXISTS '||column_record.schema_name||'.'||column_record.table_name||' (';
            ELSE
                v_table_ddl:=v_table_ddl||',';
            END IF;

            IF column_record.attnum <= column_record.max_attnum THEN
                v_table_ddl:=v_table_ddl||chr(10)||
                         '    '||column_record.column_name||' '||column_record.column_type||' '||column_record.column_default_value||' '||column_record.column_not_null;
            END IF;
        END LOOP;

        firstrec := TRUE;
        FOR constraint_rec IN
            SELECT conname, pg_get_constraintdef(c.oid) as constrainddef
                FROM pg_constraint c
                    WHERE conrelid=(
                        SELECT attrelid FROM pg_attribute
                        WHERE attrelid = (
                            SELECT oid FROM pg_class WHERE relname = table_rec.relname
                                AND relnamespace = (SELECT ns.oid FROM pg_namespace ns WHERE ns.nspname = p_schema_name)
                        ) AND attname='tableoid'
                    )
        LOOP
            v_table_ddl:=v_table_ddl||','||chr(10);
            v_table_ddl:=v_table_ddl||'CONSTRAINT '||constraint_rec.conname;
            v_table_ddl:=v_table_ddl||chr(10)||'    '||constraint_rec.constrainddef;
            firstrec := FALSE;
        END LOOP;
        v_table_ddl:=v_table_ddl||chr(10)||');';
        RETURN NEXT v_table_ddl;
    END LOOP;
END;
$BODY$
  LANGUAGE plpgsql;""";

String sqlRunFunction = "select describe_table('public', 'fw_final_base_copy');\n" +
"";
String sqlString_describe_table = q2d0.queryForStr2(sqlCreateFunction, sqlRunFunction);
String sqlString_describe_tableForFW_CUSTOM_VAR = "CREATE UNLOGGED TABLE IF NOT EXISTS public.\"" + cfg().dbName() + "\" (" +
"status boolean NULL," +
" attachment text NULL," +
" fw_var bigint NULL," +
" combi_id_final bigint NULL," +
" combi_id_optional bigint NULL," +
" \"fw_optJ\" bigint NULL" +
") TABLESPACE \"" + cfg().dbTablespaceResults() + "\";";





final String __trackerColsDdl = "status boolean NULL," +
" attachment text NULL," +
" fw_var bigint NULL," +
" combi_id_final bigint NULL," +
" combi_id_optional bigint NULL," +
" \"fw_optJ\" bigint NULL,";
sqlString_describe_table = sqlString_describe_table.replaceAll("public.fw_final_base_copy", "public.\"" + cfg().dbName() + "\"");
if (sqlString_describe_table.matches("(?s).*combi_id\\s+bigint.*")) {
sqlString_describe_table = sqlString_describe_table.replaceAll("combi_id bigint.*,", __trackerColsDdl);
} else {

sqlString_describe_table = sqlString_describe_table.replaceFirst("\\(", "( " + __trackerColsDdl);
}
sqlString_describe_table = sqlString_describe_table
.replaceAll(" smallint\\[\\]", "\" smallint[]")
.replaceAll("combos(?=\\d+_\\w+)", "\"combos")
.replaceAll("smallint\\[\\]", "boolean")
.replaceAll("\\s{2,}", " ")
.replaceAll(",", ",\n");
sqlString_describe_table = sqlString_describe_table.substring(0, sqlString_describe_table.lastIndexOf(";")) + " TABLESPACE \"" + cfg().dbTablespaceResults() + "\";";
QueryToDB q2d02 = new QueryToDB();
q2d02.init();
ResultSet rs = q2d02.queryForWholeResSet("SELECT * FROM public.\"ColumnsContainFwExitCode\";");
Map<String, Integer> columnsFW_EXIT_CODEmap = new LinkedHashMap<>();
StringBuilder sbFW_EXIT_CODEcolumns = new StringBuilder();
StringBuilder sbFW_CUSTOM_VARcolumns = new StringBuilder();
while (true) {
try {
if (!rs.next()) break;
columnsFW_EXIT_CODEmap.put(rs.getString("sheet"), rs.getInt("fw_exit_code"));
sbFW_EXIT_CODEcolumns.append("'status',").append("'attachment',").append("'fw_var',").append("'combi_id_final',").append("'combi_id_optional',").append("'fw_optJ',");
sbFW_EXIT_CODEcolumns.append("'combos").append(rs.getInt("fw_exit_code")).append("_").append(rs.getString("sheet")).append("',");
sbFW_CUSTOM_VARcolumns.append("'status',").append("'attachment',").append("'fw_var',").append("'combi_id_final',").append("'combi_id_optional',").append("'fw_optJ',");
} catch (SQLException e) {
e.printStackTrace();
}
}
if (cfg().dbFwExitCodeColumnsOnlyResults())
sbFW_EXIT_CODEcolumns.deleteCharAt(sbFW_EXIT_CODEcolumns.lastIndexOf(","));
if (cfg().dbFwCustomVarOnlyResults())
sbFW_CUSTOM_VARcolumns.deleteCharAt(sbFW_CUSTOM_VARcolumns.lastIndexOf(","));
q2d0.disconnect();
q2d02.disconnect();
QueryToDBpostgres q2db_postgres_results = new QueryToDBpostgres(DB_HOST_results, DB_PORT_results, DB_USER_results, DB_PASSWORD_results);
System.out.println("\nWARNING!!!\n DROP DATABASE IF EXISTS " + cfg().dbName() + "; @" + DB_HOST_results + ":" + DB_PORT_results + " for user " + DB_USER_results + " ?");
boolean yn = false, forceDBresCreationHardcoded = true; if(forceDBresCreationHardcoded)System.out.println("\n05062026 Y forceDBresCreationHardcoded DB drop an create at work\n"); //05062026:Y: boolean yn = false;
boolean dropAndCreateTablespace_results = false;//05062026:Y: boolean dropAndCreateTablespace_results = false;
System.out.println("WARNING! Possible data in result DB will be deleted!");
String defMessage = "(Re)create Result DB? Please type choice [default=SKIP in " + inputTimeout + " secs]:";
System.out.println(defMessage);
actualAnswer = InputWithTimeout.getChoiceWithTimeout(InputWithTimeout.Choice.N, defMessage, "[(y)es/(n)o]?", inputTimeout);
if (actualAnswer.trim().equalsIgnoreCase("y") || actualAnswer.trim().equalsIgnoreCase("yes")) {
System.out.println("You have entered [" + actualAnswer + "]. Are you sure to DROP old (and possible data there) + CREATE empty database at last???");
System.out.println("[y/n]");
Scanner __sysIn = new Scanner(System.in);
OUTER:
while (true) {
actualAnswer = __sysIn.hasNext() ? __sysIn.next().trim().toLowerCase() : "n";
switch (actualAnswer) {
case "y" -> { yn = true; break OUTER; }
case "n" -> { yn = false; break OUTER; }
default -> System.out.println("Sorry, I didn't get that. Please, enter (y/n)");
}
}
System.out.println("TABLESPACE. Drop And Create tablespace " + cfg().dbTablespaceResults() + " located at " + cfg().dbTablespaceLocationResults() + " for database " + cfg().dbName() + " @" + DB_HOST_results + ":" + DB_PORT_results + " for user " + DB_USER_results + " ?\nPlease enter your choice: [yes/no]?");
OUTER2:
while (true) {
actualAnswer = __sysIn.hasNext() ? __sysIn.next().trim().toLowerCase() : "no";
switch (actualAnswer) {
case "yes" -> { dropAndCreateTablespace_results = true; break OUTER2; }
case "no" -> { dropAndCreateTablespace_results = false; break OUTER2; }
default -> System.out.println("Sorry, I didn't get that. Please, enter (yes/no)");
}
}

if (yn || forceDBresCreationHardcoded) {
q2db_postgres_results.query("DROP DATABASE IF EXISTS \"" + cfg().dbName() + "\";");
}
if (dropAndCreateTablespace_results || forceDBresCreationHardcoded) {
q2db_postgres_results.query("DROP TABLESPACE if exists \"" + cfg().dbTablespaceResults() + "\";");
q2db_postgres_results.query("CREATE TABLESPACE \"" + cfg().dbTablespaceResults() + "\" LOCATION '" + cfg().dbTablespaceLocationResults() + "';\n");
System.out.println("Tablespace recreated");
} else System.out.println("Old Tablespace remained");
if (yn) {
q2db_postgres_results.query("CREATE DATABASE \"" + cfg().dbName() + "\" OWNER " + DB_USER_results + " TABLESPACE \"" + cfg().dbTablespaceResults() + "\";");
System.out.print("Connecting to created DB and creating result table...");
QueryToDB q2createdDb = new QueryToDB();
QueryToDB q2createdDb2 = new QueryToDB();
q2createdDb.init(DB_HOST_results, DB_PORT_results, cfg().dbName(), DB_USER_results, DB_PASSWORD_results);
if (cfg().dbFwCustomVarOnlyResults()) {
q2createdDb.query(sqlString_describe_tableForFW_CUSTOM_VAR);
if (cfg().dbFwCustomvarmapCreateTableResults()) {
DataBaseManager2 dbMgr2From = new DataBaseManager2(cfg().dbHost(), cfg().dbPort(), cfg().dbName());
dbMgr2From.setDB_USER(cfg().dbUser());
dbMgr2From.setDB_PASS(cfg().dbPassword());
DataBaseManager2 dbMgr2To = new DataBaseManager2(DB_HOST_results, DB_PORT_results, cfg().dbName());
dbMgr2To.setDB_USER(cfg().dbUser());
dbMgr2To.setDB_PASS(cfg().dbPassword());
try {
System.out.print("Creating 'customvarmap' table in DB results database and copy data into it from source 'customvarmap' table...");
dbMgr2To.execAndForget("CREATE UNLOGGED TABLE IF NOT EXISTS customvarmap (fw_custom_var int NULL, message text NULL) TABLESPACE \"" + cfg().dbTablespaceResults() + "\";");
copyTableDataBetweenDBs("customvarmap", dbMgr2From.getConnection(), dbMgr2To.getConnection());
System.out.println("Done.");
} catch (SQLException e) {
e.printStackTrace();
dbMgr2From.disconnect();
dbMgr2To.disconnect();
}
dbMgr2From.disconnect();
dbMgr2To.disconnect();
}
} else q2createdDb.query(sqlString_describe_table);

q2createdDb.disconnect();
if (cfg().dbFwExitCodeColumnsOnlyResults() && !cfg().dbFwCustomVarOnlyResults()) {
q2createdDb2.init(DB_HOST_results, DB_PORT_results, cfg().dbName(), DB_USER_results, DB_PASSWORD_results);
q2createdDb2.query(
"DO $$\n" +
"DECLARE\n" +
"    crow record;\n" +
"    excludes varchar[] := array[" + sbFW_EXIT_CODEcolumns + "];\n" +
"    yourtab varchar := '" + cfg().dbName() + "';\n" +
"BEGIN\n" +
"    FOR crow IN\n" +
"        SELECT * FROM information_schema.columns WHERE table_schema = 'public' and table_name = yourtab and column_name != ALL(excludes)\n" +
"    LOOP\n" +
"        EXECUTE format ('ALTER TABLE \"%s\" DROP COLUMN \"%s\"', yourtab, crow.column_name);\n" +
"    END LOOP;\n" +
"END;\n" +
"$$ language plpgsql"
);
q2createdDb2.disconnect();
}
System.out.println("Done.");
}
}
System.out.print("Disconnecting from postgres database @" + DB_HOST_results + ":" + DB_PORT_results + " user postgres...");
q2db_postgres_results.disconnect();
System.out.println("Done.");

try {
File file = new File(cfg().pathFwResultsDbCfgFileResults());
file.createNewFile();
// This handshake file carries the results-database password in cleartext — it is
// the credential the Executor picks up. Restrict it to the owner before writing,
// so it is protected even if the handshake directory is copied out of the run
// directory (which the run itself now creates as 0700).
restrictToOwner(file);
FileWriter myWriter = new FileWriter(cfg().pathFwResultsDbCfgFileResults());
myWriter.write("jdbc:postgresql://" + cfg().dbHostResults() + ":" + cfg().dbPortResults() + "/" + cfg().dbName() + "?user=" + cfg().dbUserResults() + "&password=" + cfg().dbPasswordResults() + "");
myWriter.close();
System.out.println("Successfully wrote resultsDbURL to the file " + cfg().pathFwResultsDbCfgFileResults());
} catch (IOException e) {
System.out.println("An error occurred.");
e.printStackTrace();
}
// BUGFIX (CREATE-DDL vs INSERT-template alignment): derive the INSERT template from the table
// that was ACTUALLY created (re-describe DB_NAME) rather than from a second regex pipeline over
// fw_final_base_copy. This block previously ran only when onlyFW_EXIT_CODEcolumns=true, so with
// that flag off the INSERT could bind per-sheet columns the created table did not have. Now it
// runs for the whole FW_VAR / FW_EXIT_CODE path; the guard keeps the create-derived DDL as a
// fallback when no result table exists (e.g. the (re)create prompt was declined).
if (!cfg().dbFwCustomVarOnlyResults()) {
try {
QueryToDB q2d03 = new QueryToDB();
q2d03.init(DB_HOST_results, DB_PORT_results, cfg().dbName(), DB_USER_results, DB_PASSWORD_results);
String __reDescribed = q2d03.queryForStr2(sqlCreateFunction, sqlRunFunction.replaceAll("fw_final_base_copy", "" + cfg().dbName() + ""));
q2d03.disconnect();
if (__reDescribed != null && __reDescribed.contains("CREATE UNLOGGED TABLE")) {
sqlString_describe_table = __reDescribed.replaceAll("public\\.", "public.\"").replaceAll("\\s*?\\(", "\" (")
.replaceAll(" TABLESPACE \\w+", "")
.replaceAll("(?<=([(,]))\\s*?(?=\\w)", " \"")
.replaceAll(" bigint ", "\" bigint ")
.replaceAll(" text ", "\" text ")
.replaceAll(" boolean ", "\" boolean ")
.replaceAll("\\s{2,}", " ")
.replaceAll(",", ",\n");
}
} catch (Exception __reDescribeEx) {
// Results table not available to re-describe (e.g. (re)create prompt declined and no prior
// table). Keep the create-derived DDL as the INSERT source instead of crashing.
System.out.println("INSERT template: could not re-describe results table (" + __reDescribeEx.getMessage() + "); keeping create-derived DDL.");
}
}

if (cfg().dbFwCustomVarOnlyResults()) {
QueryToDB q2d04 = new QueryToDB();
q2d04.init(DB_HOST_results, DB_PORT_results, cfg().dbName(), DB_USER_results, DB_PASSWORD_results);
sqlString_describe_tableForFW_CUSTOM_VAR = q2d04.queryForStr2(sqlCreateFunction, sqlRunFunction.replaceAll("fw_final_base_copy", "" + cfg().dbName() + ""));
sqlString_describe_tableForFW_CUSTOM_VAR = sqlString_describe_tableForFW_CUSTOM_VAR.replaceAll("public\\.", "public.\"").replaceAll("\\s*?\\(", "\" (")
.replaceAll(" TABLESPACE \\w+", "")
.replaceAll("(?<=([(,]))\\s*?(?=\\w)", " \"")
.replaceAll(" bigint ", "\" bigint ")
.replaceAll(" text ", "\" text ")
.replaceAll(" boolean ", "\" boolean ")
.replaceAll("\\s{2,}", " ")
.replaceAll(",", ",\n");
q2d04.disconnect();
}

sqlString_describe_table = sqlString_describe_table.replaceAll("CREATE UNLOGGED TABLE IF NOT EXISTS", "INSERT INTO")
.replaceAll("(\\s+boolean\\s+NULL)|(\\s+text\\s+NULL)|(\\s+bigint\\s+NULL)", "")
.replaceAll("(;|(?<=([)]))).*", " VALUES (" + String.join(", ", Collections.nCopies((int) (sqlString_describe_table.chars().filter(ch -> ch == ',').count() + 1), "?")) + ")");

sqlString_describe_tableForFW_CUSTOM_VAR = sqlString_describe_tableForFW_CUSTOM_VAR.replaceAll("CREATE UNLOGGED TABLE IF NOT EXISTS", "INSERT INTO")
.replaceAll("(\\s+boolean\\s+NULL)|(\\s+text\\s+NULL)|(\\s+bigint\\s+NULL)", "")
.replaceAll("(;|(?<=([)]))).*", " VALUES (" + String.join(", ", Collections.nCopies(6, "?")) + ")");

try {
FileWriter myWriter = new FileWriter(cfg().pathFwResultsDbSqlInsertTemplateFileResults());
String sqlInsertStringToWrite = (cfg().dbFwCustomVarOnlyResults()) ? sqlString_describe_tableForFW_CUSTOM_VAR : sqlString_describe_table;
myWriter.write(sqlInsertStringToWrite);
myWriter.close();
System.out.println("Successfully wrote to the file " + cfg().pathFwResultsDbSqlInsertTemplateFileResults());
} catch (IOException e) {
System.out.println("An error occurred.");
e.printStackTrace();
}

System.out.println("Done.");
if (yn) System.out.println("DB RESULTS creation: Done");
else System.out.println("DB RESULTS creation: - SKIPPED! due to user negative input answer.");
}

}
