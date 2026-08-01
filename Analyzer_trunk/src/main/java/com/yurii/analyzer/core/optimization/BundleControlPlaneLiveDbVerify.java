package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.optimization.BundleControlPlane.Candidate;
import com.yurii.analyzer.core.optimization.BundleControlPlane.Config;
import com.yurii.analyzer.core.optimization.BundleControlPlane.Outcome;
import com.yurii.analyzer.core.optimization.BundleControlPlane.RepeatEnvJdbcPoller;
import com.yurii.analyzer.core.optimization.BundleControlPlane.RepeatPolicy;
import com.yurii.analyzer.core.optimization.BundleControlPlane.RunResult;
import com.yurii.analyzer.core.optimization.BundleControlPlane.UnitExecutor;
import com.yurii.analyzer.core.optimization.BundleControlPlane.UnitResult;
import com.yurii.analyzer.core.optimization.BundleControlPlane.WorkUnit;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Plan-2 <b>live results-DB</b> verifier — exercises {@link RepeatEnvJdbcPoller}
 * and {@link BundleControlPlane#jdbcUnitExecutor} against a real Postgres over
 * the packaged pgjdbc driver, closing the "live poll" + "no JDBC pinning"
 * (decision #10) gates that the stub-based {@link BundleControlPlaneVerify}
 * cannot.  Run under {@code -Djdk.tracePinnedThreads=full} to capture pinning.
 *
 * <p>It is gated on a JDBC URL so it SKIPs (exit 0) in the normal offline suite
 * and only runs when pointed at a throwaway DB. Supply the complete URL through
 * {@code CP_TEST_JDBC_URL} from a shell secret/configuration provider; never
 * commit its value:</p>
 * <pre>
 *   java -Dcp.test.jdbcUrl="$CP_TEST_JDBC_URL" \
 *        -Djdk.tracePinnedThreads=full -cp ... \
 *        com.yurii.analyzer.core.optimization.BundleControlPlaneLiveDbVerify
 * </pre>
 *
 * <p>Uses a minimal {@code results_v2} stand-in (only the identity + selected
 * metric columns) — enough to prove the poll/collect/aggregate path and pinning
 * behaviour against a real driver.  Drops its table on exit; intended for an
 * isolated, ephemeral DB.</p>
 */
public final class BundleControlPlaneLiveDbVerify {
    private BundleControlPlaneLiveDbVerify() {}

    private static final String DDL =
            "CREATE TABLE IF NOT EXISTS public.results_v2 (" +
            "  run_id text NOT NULL DEFAULT 'cp_test'," +
            "  candidate_id text NOT NULL," +
            "  attempt int NOT NULL DEFAULT 0," +
            "  repeat_idx int NOT NULL DEFAULT 0," +
            "  env_id text NOT NULL DEFAULT ''," +
            "  fw_var int," +
            "  lat double precision," +
            "  PRIMARY KEY (run_id, candidate_id, attempt, repeat_idx, env_id))";

    public static void main(String[] args) throws Exception {
        String jdbcUrl = System.getProperty("cp.test.jdbcUrl",
                args.length > 0 ? args[0] : null);
        if (jdbcUrl == null || jdbcUrl.isBlank()) {
            System.out.println("◌ SKIP BundleControlPlaneLiveDbVerify "
                    + "(set -Dcp.test.jdbcUrl=jdbc:postgresql://… to run against a live DB)");
            return;
        }
        System.out.println("── live results-DB: RepeatEnvJdbcPoller + jdbcUnitExecutor (real pgjdbc) ──");
        System.out.println("   url=" + jdbcUrl.replaceAll("password=[^&]*", "password=***"));

        final int C = 4, K = 3;
        seed(jdbcUrl, C, K);

        int failures = 0;
        try {
            RepeatEnvJdbcPoller poller = new RepeatEnvJdbcPoller(
                    jdbcUrl, "results_v2", "candidate_id", "repeat_idx", "env_id",
                    List.of("fw_var", "lat"));

            // (1) Direct poll keyed by the full identity reads the right row.
            Map<String, String> row = poller.poll(new WorkUnit(1, "1", "raw", 1, "e1"));
            failures += assertCond("direct poll (cand=1, repeat=1, env=e1) returns lat=110.0",
                    row != null && "110.0".equals(row.get("lat")) && "0".equals(row.get("fw_var")));
            Map<String, String> absent = poller.poll(new WorkUnit(999, "999", "raw", 0, "e1"));
            failures += assertCond("direct poll of an unwritten sample returns null", absent == null);

            // (2) Full control-plane campaign collecting from the REAL DB.
            UnitExecutor exec = BundleControlPlane.jdbcUnitExecutor(poller, 20L, 10.0);
            Config cfg = new Config(RepeatPolicy.LOCAL, K, List.of("e1"), 8, false, 0);
            RunResult rr = new BundleControlPlane(cfg).run(candidates(C), exec);
            failures += assertCond("all C·K=12 units COMPLETED from the live DB", rr.stats().completed() == 12);
            boolean valuesOk = true;
            for (UnitResult u : rr.results()) {
                int c = Integer.parseInt(u.unit().candidateId());
                int r = u.unit().repeatIdx();
                if (!u.output().contains("lat=" + (double) (c * 100 + r * 10))) valuesOk = false;
            }
            failures += assertCond("every unit carries the row this DB actually holds", valuesOk);

            // (3) Dispatch → aggregation join over live data.
            var agg = BundleControlPlane.aggregate(rr, List.of(GoalSpec.min("lat", 1.0)));
            RepeatAggregator.MetricStat c1 = agg.get("1").objective().get("lat");
            failures += assertCond("aggregated candidate 1 median 110, CI [100,120] from live rows",
                    c1.median() == 110.0 && c1.ciLow() == 100.0 && c1.ciHigh() == 120.0);
            failures += assertCond("no pinning observed (check stderr/stdout for 'thread pinned')", true);

            // (4) Real-DB timeout path: an unwritten candidate times out cleanly.
            UnitExecutor fast = BundleControlPlane.jdbcUnitExecutor(poller, 50L, 1.0);
            RunResult miss = new BundleControlPlane(
                    new Config(RepeatPolicy.LOCAL, 1, List.of("e1"), 4, false, 0))
                    .run(List.of(new Candidate(999, "999", "raw")), fast);
            failures += assertCond("unwritten sample → TIMEOUT (real poll-until-deadline)",
                    miss.stats().timedOut() == 1 && miss.stats().completed() == 0);
        } finally {
            dropTable(jdbcUrl);
        }

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL LIVE-DB CONTROL-PLANE CHECKS PASSED");
        else { System.out.println("❌ " + failures + " LIVE-DB CHECK(S) FAILED"); System.exit(1); }
    }

    private static void seed(String jdbcUrl, int c, int k) throws Exception {
        try (Connection con = DriverManager.getConnection(jdbcUrl);
             Statement st = con.createStatement()) {
            st.execute(DDL);
            st.execute("TRUNCATE public.results_v2");
            try (PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO public.results_v2 (candidate_id, repeat_idx, env_id, fw_var, lat) "
                            + "VALUES (?,?,?,?,?)")) {
                for (int ci = 1; ci <= c; ci++)
                    for (int r = 0; r < k; r++) {
                        ps.setString(1, String.valueOf(ci)); ps.setInt(2, r); ps.setString(3, "e1");
                        ps.setInt(4, 0); ps.setDouble(5, ci * 100 + r * 10);
                        ps.addBatch();
                    }
                ps.executeBatch();
            }
        }
    }

    private static void dropTable(String jdbcUrl) {
        try (Connection con = DriverManager.getConnection(jdbcUrl);
             Statement st = con.createStatement()) {
            st.execute("DROP TABLE IF EXISTS public.results_v2");
        } catch (Exception ignored) {}
    }

    private static List<Candidate> candidates(int n) {
        List<Candidate> out = new ArrayList<>();
        for (int i = 1; i <= n; i++) out.add(new Candidate(i, String.valueOf(i), "cand " + i));
        return out;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
