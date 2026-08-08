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

package com.company.db.sql;

import com.company.db.DbClient;
import net.sf.jsqlparser.expression.BooleanValue;
import net.sf.jsqlparser.expression.DateValue;
import net.sf.jsqlparser.expression.DoubleValue;
import net.sf.jsqlparser.expression.Expression;
import net.sf.jsqlparser.expression.Function;
import net.sf.jsqlparser.expression.JdbcNamedParameter;
import net.sf.jsqlparser.expression.JdbcParameter;
import net.sf.jsqlparser.expression.LongValue;
import net.sf.jsqlparser.expression.NullValue;
import net.sf.jsqlparser.expression.StringValue;
import net.sf.jsqlparser.expression.TimeValue;
import net.sf.jsqlparser.expression.TimestampValue;
import net.sf.jsqlparser.expression.operators.relational.ParenthesedExpressionList;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.schema.Column;
import net.sf.jsqlparser.statement.Statement;
import net.sf.jsqlparser.statement.insert.Insert;
import net.sf.jsqlparser.statement.select.Values;
import net.sf.jsqlparser.statement.update.Update;
import net.sf.jsqlparser.statement.update.UpdateSet;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.regex.Matcher;
import java.util.regex.Pattern;


public final class SqlSelfHealingExecutor {

    private static final Logger log = LogManager.getLogger(SqlSelfHealingExecutor.class);


    public static final String UNDEFINED_COLUMN = "42703";

    private static final Pattern MISSING_COLUMN_MSG = Pattern.compile(
            "column\\s+\"([^\"]+)\"\\s+of\\s+relation\\s+\"([^\"]+)\"\\s+does\\s+not\\s+exist",
            Pattern.CASE_INSENSITIVE);

    private final DbClient               db;
    private final TimeoutSqlExecutor     executor;
    private final RelationLockRegistry   lockRegistry;

    public SqlSelfHealingExecutor(DbClient db, TimeoutSqlExecutor executor) {
        this(db, executor, null);
    }


    public SqlSelfHealingExecutor(DbClient db,
                                  TimeoutSqlExecutor executor,
                                  RelationLockRegistry lockRegistry) {
        if (db == null)       throw new IllegalArgumentException("db must not be null");
        if (executor == null) throw new IllegalArgumentException("executor must not be null");
        this.db           = db;
        this.executor     = executor;
        this.lockRegistry = lockRegistry;
    }


    public void executeWithSelfHeal(String sql) throws SQLException {
        executeWithSelfHeal(sql, null);
    }


    public void executeWithSelfHeal(String sql, String knownTargetRelation) throws SQLException {
        final String hardened = LegacySqlHardener.HARDEN.apply(sql);
        /*Ylog.info*/log.debug("[Y] self-heal: about to execute (length={}, target={})\n{}",
                hardened == null ? 0 : hardened.length(),
                knownTargetRelation == null ? "<unlocked>" : knownTargetRelation,
                hardened);

        final ReadWriteLock rw = (lockRegistry != null && knownTargetRelation != null)
                ? lockRegistry.get(knownTargetRelation) : null;
        final Lock readLock  = rw == null ? null : rw.readLock();
        final Lock writeLock = rw == null ? null : rw.writeLock();

        if (readLock != null) readLock.lock();
        boolean readHeld = readLock != null;
        try {
            int budget = computeRetryBudget(hardened);
            SQLException lastError = null;

            for (int attempt = 0; attempt < budget; attempt++) {
                try {
                    /*Ylog.info*/log.debug("[Y] self-heal attempt {} of {} (target={})",
                            attempt + 1, budget,
                            knownTargetRelation == null ? "<unlocked>" : knownTargetRelation);
                    executor.execute(hardened);
                    /*Ylog.info*/log.debug("[Y] self-heal: SQL executed successfully");
                    return;
                } catch (SQLException sqle) {
                    if (!UNDEFINED_COLUMN.equals(sqle.getSQLState())) {
                        log.error("[Y] self-heal: non-42703 error — propagating", sqle);
                        throw sqle;
                    }
                    lastError = sqle;




                    if (readHeld) { readLock.unlock(); readHeld = false; }

                    if (writeLock != null) writeLock.lock();
                    try {
                        hotFixOrThrow(sqle, hardened);
                    } finally {
                        if (writeLock != null) writeLock.unlock();
                    }


                    if (readLock != null) { readLock.lock(); readHeld = true; }
                }
            }
            throw new SQLException(
                    "[Y] self-heal: exhausted retry budget (" + budget + ") without success",
                    lastError);
        } finally {
            if (readHeld) readLock.unlock();
        }
    }


    private static int computeRetryBudget(String sql) {
        if (sql == null) return 1;
        int open  = sql.indexOf('(');
        int close = open >= 0 ? sql.indexOf(')', open + 1) : -1;
        if (open < 0 || close <= open) return 1;
        String[] cols = sql.substring(open + 1, close).split(",");
        return Math.max(cols.length, 1);
    }

    private void hotFixOrThrow(SQLException sqle, String hardenedSql) throws SQLException {
        String errMsg = sqle.getMessage() == null ? "" : sqle.getMessage();
        Matcher m = MISSING_COLUMN_MSG.matcher(errMsg);
        if (!m.find()) {
            throw sqle;
        }
        String missingColumn = m.group(1);
        String relation      = m.group(2);

        log.warn("[Y] self-heal: 42703 detected — missingColumn='{}' relation='{}'",
                missingColumn, relation);

        Connection conn = null;
        boolean restoreAutoCommit = false;
        try {
            conn = db.getConnection();
            restoreAutoCommit = conn.getAutoCommit();
            if (restoreAutoCommit) {
                conn.setAutoCommit(false);
            }
            try { conn.rollback(); } catch (Exception ignored) {  }

            new TableRebuilder(conn, hardenedSql, missingColumn, relation).rebuild();

            if (restoreAutoCommit) {
                conn.commit();
            }
            /*Ylog.info*/log.debug("[Y] self-heal: hot-fix succeeded for column '{}' in '{}'",
                    missingColumn, relation);
        } catch (SQLException sqlEx) {
            rollbackQuietly(conn);
            log.warn("[Y] self-heal: hot-fix failed for missing column '{}' in '{}'",
                    missingColumn, relation, sqlEx);
            throw sqle;
        } catch (Exception ex) {
            rollbackQuietly(conn);
            log.warn("[Y] self-heal: unexpected hot-fix failure for '{}' in '{}'",
                    missingColumn, relation, ex);
            throw new SQLException(ex);
        } finally {
            if (conn != null) {
                try { conn.setAutoCommit(restoreAutoCommit); } catch (Exception ignored) {  }
                try { conn.close();                          } catch (Exception ignored) {  }
            }
        }
    }

    private static void rollbackQuietly(Connection conn) {
        if (conn == null) return;
        try { conn.rollback(); }
        catch (Exception rollbackEx) { log.error("[Y] rollback after hot-fix failure also failed", rollbackEx); }
    }






    static String normalizeId(String s) {
        return s == null ? null : s.replace("\"", "").trim();
    }


    static String quoteIdent(String s) {
        return "\"" + (s == null ? "" : s.replace("\"", "\"\"")) + "\"";
    }


    static String quoteQualifiedName(String name) {
        if (name == null || name.isBlank()) return "\"\"";
        String[] parts = name.split("\\.");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < parts.length; i++) {
            if (i > 0) sb.append('.');
            sb.append(quoteIdent(normalizeId(parts[i])));
        }
        return sb.toString();
    }






    static final class PgTypeInferrer {

        private static final Pattern PG_CAST_NUMERIC =
                Pattern.compile("::\\s*([a-zA-Z_][a-zA-Z0-9_\\s\\[\\]]*)");

        private static final Pattern PG_CAST_FUNCTIONAL =
                Pattern.compile("cast\\s*\\(.*\\s+as\\s+([a-zA-Z_][a-zA-Z0-9_\\s\\[\\]]*)\\s*\\)");

        private static final Pattern SMALLINT_ARRAY_LITERAL =
                Pattern.compile("^'\\s*\\{[\\d\\s,\\-]*\\}\\s*'.*");

        String infer(Expression expression) {
            if (expression == null) return "TEXT";

            if (expression instanceof ParenthesedExpressionList<?> list) {
                for (Object item : list) {
                    if (item instanceof Expression ex) {
                        String inferred = infer(ex);
                        if (!"TEXT".equals(inferred)) return inferred;
                    }
                }
                return "TEXT";
            }

            if (expression instanceof StringValue sv) {
                String val = sv.getValue();
                if (val != null) {
                    String trimmed = val.trim();
                    if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
                        String inner = trimmed.substring(1, trimmed.length() - 1);
                        if (inner.matches("^[\\d\\s,\\-]*$")) return "smallint[]";
                    }
                }
                return "TEXT";
            }
            if (expression instanceof LongValue lv) {
                long v = lv.getValue();
                return (v >= Integer.MIN_VALUE && v <= Integer.MAX_VALUE) ? "INTEGER" : "BIGINT";
            }
            if (expression instanceof DoubleValue)    return "DOUBLE PRECISION";
            if (expression instanceof BooleanValue)   return "BOOLEAN";
            if (expression instanceof DateValue)      return "DATE";
            if (expression instanceof TimeValue)      return "TIME";
            if (expression instanceof TimestampValue) return "TIMESTAMP";
            if (expression instanceof NullValue)      return "TEXT";
            if (expression instanceof JdbcParameter || expression instanceof JdbcNamedParameter) {
                return "TEXT";
            }

            if (expression instanceof Function fn) {
                String fnName = fn.getName();
                if (fnName != null) {
                    String lower = fnName.toLowerCase(Locale.ROOT);
                    if (lower.contains("uuid")) return "UUID";
                    if (lower.contains("jsonb")) return "JSONB";
                    if (lower.contains("json"))  return "JSON";
                    if (lower.contains("now") || lower.contains("current_timestamp")) {
                        return "TIMESTAMP";
                    }
                }
            }

            String raw = expression.toString();
            if (raw != null) {
                String normalized = raw.toLowerCase(Locale.ROOT);
                Matcher castMatcher = PG_CAST_NUMERIC.matcher(normalized);
                if (castMatcher.find()) return castMatcher.group(1).trim().toUpperCase(Locale.ROOT);
                Matcher functionalCast = PG_CAST_FUNCTIONAL.matcher(normalized);
                if (functionalCast.find()) return functionalCast.group(1).trim().toUpperCase(Locale.ROOT);
                if (raw.trim().matches(SMALLINT_ARRAY_LITERAL.pattern())) return "smallint[]";
                if (normalized.contains("uuid"))  return "UUID";
                if (normalized.contains("jsonb")) return "JSONB";
                if (normalized.contains("json"))  return "JSON";
            }

            return "TEXT";
        }
    }


    static final class ColumnDef {
        String columnName;
        String dataType;
        Integer characterMaximumLength;
        Integer numericPrecision;
        Integer numericScale;
        Integer datetimePrecision;
        String  isNullable;
        String  columnDefault;
        String  isIdentity;
        String  identityGeneration;
        String  collationName;
        String  udtName;
        String  domainName;
        String  domainSchema;


        String ddl() {
            String dt = dataType == null ? "text" : dataType.trim();
            String dtLower = dt.toLowerCase(Locale.ROOT);
            String typeSql;
            String lengthPart    = (characterMaximumLength != null && characterMaximumLength > 0)
                    ? "(" + characterMaximumLength + ")" : "";
            String numericPart   = (numericPrecision != null)
                    ? (numericScale != null
                        ? "(" + numericPrecision + "," + numericScale + ")"
                        : "(" + numericPrecision + ")")
                    : "";
            String precisionPart = (datetimePrecision != null)
                    ? "(" + datetimePrecision + ")" : "";

            if (domainName != null && !domainName.isBlank()) {
                typeSql = (domainSchema != null && !domainSchema.isBlank())
                        ? quoteIdent(domainSchema) + "." + quoteIdent(domainName)
                        : quoteIdent(domainName);
            } else {
                typeSql = switch (dtLower) {
                    case "character varying", "varchar"        -> "VARCHAR" + lengthPart;
                    case "character", "char"                   -> "CHAR" + lengthPart;
                    case "bit varying"                          -> "BIT VARYING" + lengthPart;
                    case "numeric", "decimal"                   -> "NUMERIC" + numericPart;
                    case "timestamp without time zone"          -> "TIMESTAMP" + precisionPart;
                    case "timestamp with time zone"             -> "TIMESTAMP" + precisionPart + " WITH TIME ZONE";
                    case "time without time zone"               -> "TIME" + precisionPart;
                    case "time with time zone"                  -> "TIME" + precisionPart + " WITH TIME ZONE";
                    case "interval"                              -> "INTERVAL" + precisionPart;
                    default -> (udtName != null && !udtName.isBlank()) ? udtName : dt;
                };
            }

            StringBuilder ddl = new StringBuilder();
            ddl.append(quoteIdent(columnName)).append(' ').append(typeSql);

            if (collationName != null && !collationName.isBlank()) {
                ddl.append(" COLLATE ").append(quoteIdent(collationName));
            }
            if (columnDefault != null && !columnDefault.isBlank()) {
                ddl.append(" DEFAULT ").append(columnDefault);
            }
            if ("NO".equalsIgnoreCase(isNullable)) {
                ddl.append(" NOT NULL");
            }
            if ("YES".equalsIgnoreCase(isIdentity)) {
                ddl.append("ALWAYS".equalsIgnoreCase(identityGeneration)
                        ? " GENERATED ALWAYS AS IDENTITY"
                        : " GENERATED BY DEFAULT AS IDENTITY");
            }
            return ddl.toString();
        }
    }


    static final class ConstraintDef {
        String name;
        String definition;
        String type;
    }


    private static final class TableRebuilder {

        private final Connection conn;
        private final String     hardenedSql;
        private final String     missingColumn;
        private final String     relation;
        private final PgTypeInferrer inferrer = new PgTypeInferrer();

        TableRebuilder(Connection conn, String hardenedSql,
                       String missingColumn, String relation) {
            this.conn          = conn;
            this.hardenedSql   = hardenedSql;
            this.missingColumn = missingColumn;
            this.relation      = relation;
        }

        void rebuild() throws Exception {

            ParseResult parsed = parseStatement();


            ResolvedRelation rel = resolveRelation();


            List<ColumnDef> currentColumns = readColumns(rel);
            if (currentColumns.isEmpty()) {
                throw new SQLException(
                        "Could not read column metadata for " + rel.qualifiedRaw()
                                + " — relation may not exist or pool may be on a different schema");
            }








            boolean alreadyExists = currentColumns.stream()
                    .anyMatch(c -> c.columnName != null
                            && c.columnName.equalsIgnoreCase(missingColumn));
            if (alreadyExists) {
                /*Ylog.info*/log.debug("[Y] table-rebuilder: column '{}' already exists in '{}' "
                                + "(rebuilt by another thread); skipping",
                        missingColumn, rel.qualifiedRaw());
                return;
            }



            String inferredType = parsed.inferredType;
            if (parsed.statement instanceof Insert insert && insert.getSelect() != null
                    && parsed.targetIndex >= 0) {
                String refined = probeSelectMetadata(insert, parsed.targetIndex);
                if (refined != null) inferredType = refined;
            }
            /*Ylog.info*/log.debug("[Y] table-rebuilder: inferredType='{}' for column '{}' in '{}'",
                    inferredType, missingColumn, rel.qualifiedRaw());


            int targetIndex = (parsed.targetIndex < 0 || parsed.targetIndex > currentColumns.size())
                    ? currentColumns.size() : parsed.targetIndex;

            List<ColumnDef> reordered = reorderWithMissing(currentColumns, alreadyExists,
                    targetIndex, inferredType);


            List<ConstraintDef> constraints = readConstraints(rel);



            String rebuildSuffix = "__rebuild_" + System.currentTimeMillis();
            String backupSuffix  = "__backup_"  + System.currentTimeMillis();
            String tempName      = rel.table + rebuildSuffix;
            String backupName    = rel.table + backupSuffix;

            String qualifiedOrig   = quoteQualifiedName(rel.schema + "." + rel.table);
            String qualifiedTemp   = quoteQualifiedName(rel.schema + "." + tempName);
            String qualifiedBackup = quoteQualifiedName(rel.schema + "." + backupName);


            executeDdl(buildCreateTableSql(qualifiedTemp, reordered));


            executeDdl(buildInsertCopySql(qualifiedTemp, qualifiedOrig, reordered,
                    alreadyExists, inferredType));


            for (ConstraintDef c : constraints) {
                if (c == null || c.definition == null || c.definition.isBlank()) continue;
                if ("n".equalsIgnoreCase(c.type)) continue;
                String renamed = c.name + rebuildSuffix;
                executeDdl("ALTER TABLE " + qualifiedTemp
                        + " ADD CONSTRAINT " + quoteIdent(renamed) + " " + c.definition);
            }


            executeDdl("ALTER TABLE " + qualifiedOrig + " RENAME TO " + quoteIdent(backupName));
            executeDdl("ALTER TABLE " + qualifiedTemp + " RENAME TO " + quoteIdent(rel.table));
            rebindOwnedSequences(rel, reordered);
            executeDdl("DROP TABLE IF EXISTS " + qualifiedBackup + " CASCADE");
        }



        private ParseResult parseStatement() throws Exception {
            Statement stmt = CCJSqlParserUtil.parse(hardenedSql,
                    parser -> parser.withAllowComplexParsing(true));

            int targetIndex = -1;
            String inferredType = "TEXT";

            if (stmt instanceof Insert insert) {
                List<Column> columns = insert.getColumns();
                if (columns != null) {
                    for (int i = 0; i < columns.size(); i++) {
                        String current = normalizeId(columns.get(i).getColumnName());
                        if (current != null && current.equalsIgnoreCase(normalizeId(missingColumn))) {
                            targetIndex = i;
                            break;
                        }
                    }
                }
                if (insert.getSelect() instanceof Values values && targetIndex >= 0) {
                    List<?> exprs = values.getExpressions();
                    if (exprs != null && targetIndex < exprs.size()) {
                        Object item = exprs.get(targetIndex);
                        if (item instanceof Expression ex) {
                            inferredType = inferrer.infer(ex);
                        } else if (item instanceof ParenthesedExpressionList<?> list) {
                            for (Object nested : list) {
                                if (nested instanceof Expression ex2) {
                                    inferredType = inferrer.infer(ex2);
                                    break;
                                }
                            }
                        }
                    }
                }
            } else if (stmt instanceof Update update) {
                List<UpdateSet> sets = update.getUpdateSets();
                if (sets != null) {
                    outer:
                    for (UpdateSet set : sets) {
                        List<Column> setColumns = set.getColumns();
                        List<?> setValues       = set.getValues();
                        if (setColumns == null || setValues == null) continue;
                        for (int i = 0; i < setColumns.size(); i++) {
                            String current = normalizeId(setColumns.get(i).getColumnName());
                            if (current != null && current.equalsIgnoreCase(normalizeId(missingColumn))) {
                                targetIndex = i;
                                Object valueObj = i < setValues.size() ? setValues.get(i) : null;
                                inferredType = (valueObj instanceof Expression ex)
                                        ? inferrer.infer(ex) : "TEXT";
                                break outer;
                            }
                        }
                    }
                }
            }
            return new ParseResult(stmt, targetIndex, inferredType);
        }


        private String probeSelectMetadata(Insert insert, int targetIndex) {
            String selectSql = insert.getSelect().toString();
            String safeSelect = "SELECT * FROM (" + selectSql + ") AS probe_subquery LIMIT 1";
            try (java.sql.Statement probe = conn.createStatement();
                 ResultSet rsProbe = probe.executeQuery(safeSelect)) {
                ResultSetMetaData rsmd = rsProbe.getMetaData();
                if (targetIndex < rsmd.getColumnCount()) {
                    String typeName = rsmd.getColumnTypeName(targetIndex + 1);
                    String mapped = mapJdbcArrayType(typeName);
                    if (mapped != null) return mapped;
                }
                if (rsProbe.next()) {
                    String val = rsProbe.getString(targetIndex + 1);
                    if (val != null) {
                        String trimmed = val.trim();
                        if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
                            String inner = trimmed.substring(1, trimmed.length() - 1);
                            if (inner.matches("^[\\d\\s,\\-]*$")) return "smallint[]";
                        }
                    }
                }
            } catch (Exception probeFail) {
                log.debug("[Y] table-rebuilder: SELECT probe failed (non-fatal): {}",
                        probeFail.getMessage());
            }
            return null;
        }

        private static String mapJdbcArrayType(String typeName) {
            if (typeName == null) return null;
            return switch (typeName.toLowerCase(Locale.ROOT)) {
                case "_int2"               -> "smallint[]";
                case "_int4"               -> "integer[]";
                case "_int8"               -> "bigint[]";
                case "_text", "_varchar"   -> "text[]";
                case "unknown", ""         -> null;
                default                    -> typeName;
            };
        }



        private ResolvedRelation resolveRelation() throws SQLException {
            String schema;
            String table;
            if (relation.contains(".")) {
                String[] parts = relation.split("\\.", 2);
                schema = normalizeId(parts[0]);
                table  = normalizeId(parts[1]);
            } else {
                table  = normalizeId(relation);
                schema = conn.getSchema();
                if (schema == null || schema.isBlank()) {
                    try (java.sql.Statement st = conn.createStatement();
                         ResultSet rs = st.executeQuery("select current_schema()")) {
                        if (rs.next()) schema = rs.getString(1);
                    }
                }
            }
            return new ResolvedRelation(schema, table);
        }



        private List<ColumnDef> readColumns(ResolvedRelation rel) throws SQLException {
            List<ColumnDef> result = new ArrayList<>();
            String sql =
                    "select column_name, data_type, character_maximum_length, numeric_precision, "
                  + "numeric_scale, datetime_precision, is_nullable, column_default, is_identity, "
                  + "identity_generation, collation_name, udt_name, domain_name, domain_schema "
                  + "from information_schema.columns "
                  + "where table_schema = ? and table_name = ? "
                  + "order by ordinal_position";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setString(1, rel.schema);
                ps.setString(2, rel.table);
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        ColumnDef c = new ColumnDef();
                        c.columnName             = rs.getString("column_name");
                        c.dataType               = rs.getString("data_type");
                        c.characterMaximumLength = nullableInt(rs, "character_maximum_length");
                        c.numericPrecision       = nullableInt(rs, "numeric_precision");
                        c.numericScale           = nullableInt(rs, "numeric_scale");
                        c.datetimePrecision      = nullableInt(rs, "datetime_precision");
                        c.isNullable             = rs.getString("is_nullable");
                        c.columnDefault          = rs.getString("column_default");
                        c.isIdentity             = rs.getString("is_identity");
                        c.identityGeneration     = rs.getString("identity_generation");
                        c.collationName          = rs.getString("collation_name");
                        c.udtName                = rs.getString("udt_name");
                        c.domainName             = rs.getString("domain_name");
                        c.domainSchema           = rs.getString("domain_schema");
                        result.add(c);
                    }
                }
            }
            return result;
        }

        private static Integer nullableInt(ResultSet rs, String column) throws SQLException {
            int n = rs.getInt(column);
            return rs.wasNull() ? null : n;
        }



        private List<ConstraintDef> readConstraints(ResolvedRelation rel) throws SQLException {
            List<ConstraintDef> result = new ArrayList<>();
            String sql =
                    "select c.conname, c.contype, pg_get_constraintdef(c.oid) as condef "
                  + "from pg_constraint c "
                  + "join pg_class t on t.oid = c.conrelid "
                  + "join pg_namespace n on n.oid = t.relnamespace "
                  + "where n.nspname = ? and t.relname = ? and c.contype <> 'n' "
                  + "order by c.contype, c.conname";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setString(1, rel.schema);
                ps.setString(2, rel.table);
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        ConstraintDef c = new ConstraintDef();
                        c.name       = rs.getString("conname");
                        c.type       = rs.getString("contype");
                        c.definition = rs.getString("condef");
                        result.add(c);
                    }
                }
            }
            return result;
        }



        private List<ColumnDef> reorderWithMissing(List<ColumnDef> current,
                                                   boolean alreadyExists,
                                                   int targetIndex,
                                                   String inferredType) {
            List<ColumnDef> out = new ArrayList<>(current.size() + 1);
            if (alreadyExists) {
                out.addAll(current);
                return out;
            }
            for (int i = 0; i < current.size(); i++) {
                if (i == targetIndex) {
                    out.add(buildMissingColumn(inferredType));
                }
                out.add(current.get(i));
            }
            if (targetIndex == current.size()) {
                out.add(buildMissingColumn(inferredType));
            }
            return out;
        }

        private ColumnDef buildMissingColumn(String inferredType) {
            ColumnDef missing = new ColumnDef();
            missing.columnName = missingColumn;
            missing.dataType   = (inferredType == null || inferredType.isBlank()) ? "TEXT" : inferredType;
            missing.isNullable = "YES";
            return missing;
        }



        private static String buildCreateTableSql(String qualifiedTemp, List<ColumnDef> cols) {
            StringBuilder sb = new StringBuilder();
            sb.append("CREATE TABLE ").append(qualifiedTemp).append(" (\n");
            for (int i = 0; i < cols.size(); i++) {
                if (i > 0) sb.append(",\n");
                sb.append("    ").append(cols.get(i).ddl());
            }
            sb.append("\n)");
            return sb.toString();
        }

        private String buildInsertCopySql(String qualifiedTemp, String qualifiedOrig,
                                          List<ColumnDef> cols, boolean alreadyExists,
                                          String inferredType) {
            StringBuilder sb = new StringBuilder();
            sb.append("INSERT INTO ").append(qualifiedTemp).append(" (");
            for (int i = 0; i < cols.size(); i++) {
                if (i > 0) sb.append(", ");
                sb.append(quoteIdent(cols.get(i).columnName));
            }
            sb.append(") SELECT ");
            for (int i = 0; i < cols.size(); i++) {
                if (i > 0) sb.append(", ");
                ColumnDef c = cols.get(i);
                if (!alreadyExists && c.columnName != null
                        && c.columnName.equalsIgnoreCase(missingColumn)) {
                    String nullType = (inferredType == null || inferredType.isBlank()) ? "TEXT" : inferredType;
                    sb.append("NULL::").append(nullType);
                } else {
                    sb.append(quoteIdent(c.columnName));
                }
            }
            sb.append(" FROM ").append(qualifiedOrig);
            return sb.toString();
        }



        private void rebindOwnedSequences(ResolvedRelation rel, List<ColumnDef> cols) throws SQLException {
            try (java.sql.Statement st = conn.createStatement()) {
                Pattern seqPattern = Pattern.compile("nextval\\('([^']+)'");
                for (ColumnDef c : cols) {
                    if (c.columnDefault == null) continue;
                    Matcher m = seqPattern.matcher(c.columnDefault);
                    if (!m.find()) continue;
                    String seqName = m.group(1);
                    String alterSeq = "ALTER SEQUENCE " + seqName
                            + " OWNED BY " + quoteQualifiedName(rel.schema + "." + rel.table)
                            + "." + quoteIdent(c.columnName);
                    try { st.execute(alterSeq); }
                    catch (Exception ignored) {  }
                }
            }
        }



        private void executeDdl(String sql) throws SQLException {
            try (java.sql.Statement st = conn.createStatement()) {
                st.execute(sql);
            }
        }



        private record ResolvedRelation(String schema, String table) {
            String qualifiedRaw() { return schema + "." + table; }
        }

        private record ParseResult(Statement statement, int targetIndex, String inferredType) {}
    }
}
