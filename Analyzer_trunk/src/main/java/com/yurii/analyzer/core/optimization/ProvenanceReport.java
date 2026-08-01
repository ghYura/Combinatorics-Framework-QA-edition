package com.yurii.analyzer.core.optimization;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/**
 * STEP 39 — provenance + non-dominance explanation for the Analyzer's selected
 * (Pareto-front) candidates. Every selected result is made explainable and
 * traceable back to its source/result row, WITHOUT loading the full corpus into
 * memory — the explanation is built from the bounded {@link Snapshot} (front +
 * retained top-K) and each candidate's own metric line (a ref, not its source).
 *
 * Output is a single VERSIONED JSON document ({@code analyzer.provenance/v1}).
 * Per selected candidate it carries:
 *   <ul>
 *     <li>candidate ID (explicit {@code candidate_id}/{@code combi_id}/{@code id}
 *         token, else a deterministic id derived from the dimension tokens — the
 *         fw_final combination that IS the result row);</li>
 *     <li>dimensions / optional-action reference (the categorical tokens);</li>
 *     <li>outcome / verdict (FW_VAR);</li>
 *     <li>objective values (the declared goal keys);</li>
 *     <li>dominating/dominated relation summary (dominated_by + dominates count
 *         over the retained comparison set);</li>
 *     <li>the reason it is non-dominated.</li>
 *   </ul>
 *
 * Formal mode applies a provenance policy: a selected candidate with no explicit
 * id is a WARNING (the id was derived from its dimensions) and one with no
 * identity at all (no id, no dimensions) is an ERROR — recorded in
 * {@code provenance_issues}. The candidate ordering is sorted (candidate_id,
 * line_no) so the report is deterministic across runs.
 */
public final class ProvenanceReport {
    private ProvenanceReport() {}

    public static final String SCHEMA = "analyzer.provenance/v1";

    private static final Set<String> ID_KEYS = Set.of("candidate_id", "combi_id", "id");
    private static final double WORST = Double.POSITIVE_INFINITY;

    /** Parsed provenance of one candidate metric line. */
    public record Provenance(String candidateId, boolean explicitId, String runId, String sourceRef,
                             Map<String, String> dimensions, Integer verdict,
                             Map<String, Double> objectives) {}

    /** Parse one K=V metric line into its provenance, given the declared goals
     *  (numeric tokens whose key is a goal become objective values; other numeric
     *  tokens are metrics and ignored here; non-numeric tokens are dimensions). */
    public static Provenance parse(String line, List<GoalSpec> goals) {
        Set<String> goalKeys = new java.util.HashSet<>();
        for (GoalSpec g : goals) goalKeys.add(g.key());
        String explicit = null, runId = null, sourceRef = null;
        Integer verdict = null;
        Map<String, String> dims = new TreeMap<>();          // sorted → deterministic
        Map<String, Double> objectives = new LinkedHashMap<>();
        for (String tok : (line == null ? "" : line).trim().split("\\s+")) {
            int eq = tok.indexOf('=');
            if (eq <= 0) continue;
            String k = tok.substring(0, eq), v = tok.substring(eq + 1);
            if (explicit == null && ID_KEYS.contains(k)) { explicit = v; continue; }
            if (k.equals("run_id")) { runId = v; continue; }
            if (k.equals("source_ref") || k.equals("source")) { sourceRef = v; continue; }
            if (k.equals("FW_VAR")) {
                try { verdict = Integer.valueOf(v.trim()); } catch (NumberFormatException ignored) {}
                continue;
            }
            java.util.OptionalDouble num = AnalyzerCore.tryParseNumeric(v);
            if (num.isPresent()) {
                if (goalKeys.contains(k)) objectives.put(k, num.getAsDouble());
            } else {
                dims.put(k, v);
            }
        }
        boolean isExplicit = explicit != null;
        String id = isExplicit ? explicit : (dims.isEmpty() ? null : deriveId(dims));
        return new Provenance(id, isExplicit, runId, sourceRef, dims, verdict, objectives);
    }

    /** Deterministic id from the (sorted) dimension tokens — the fw_final
     *  combination that identifies the result row. */
    public static String deriveId(Map<String, String> dims) {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : dims.entrySet())
            sb.append(e.getKey()).append('=').append(e.getValue()).append(';');
        long h = 1125899906842597L;                          // FNV-ish stable hash
        for (int i = 0; i < sb.length(); i++) h = 31 * h + sb.charAt(i);
        return "dim:" + Long.toHexString(h & 0xffffffffffffffL);
    }

    /** Build the versioned provenance report for the snapshot's Pareto front. */
    public static ObjectNode build(Snapshot snap, List<GoalSpec> goals, boolean formal) {
        ObjectNode root = AnalyzerCore.mapper().createObjectNode();
        root.put("schema", SCHEMA);
        root.put("mode", formal ? "formal" : "exploratory");
        root.put("candidates_seen", snap.updates());
        ArrayNode goalsArr = root.putArray("goals");
        for (GoalSpec g : goals) {
            ObjectNode gn = goalsArr.addObject();
            gn.put("key", g.key());
            gn.put("mode", g.mode().name());
        }

        List<LineResult> front = snap.paretoFront();
        List<LineResult> cmp = snap.topByScore();            // bounded retained comparison set

        // Pre-parse front provenance once (id + objectives reused for reason/dominance).
        List<Map.Entry<LineResult, Provenance>> rows = new ArrayList<>();
        for (LineResult r : front) rows.add(Map.entry(r, parse(r.originalLine, goals)));
        // deterministic order: by candidate_id then line_no
        rows.sort(Comparator
                .comparing((Map.Entry<LineResult, Provenance> e) ->
                        e.getValue().candidateId() == null ? "" : e.getValue().candidateId())
                .thenComparingInt(e -> e.getKey().lineNo));

        ArrayNode cands = root.putArray("candidates");
        ArrayNode issues = root.putArray("provenance_issues");
        for (Map.Entry<LineResult, Provenance> e : rows) {
            LineResult r = e.getKey();
            Provenance p = e.getValue();
            ObjectNode c = cands.addObject();
            c.put("candidate_id", p.candidateId());
            c.put("provenance", p.explicitId() ? "explicit"
                    : (p.candidateId() != null ? "derived-from-dimensions" : "missing"));
            if (p.runId() != null) c.put("run_id", p.runId());
            if (p.sourceRef() != null) c.put("source_ref", p.sourceRef());
            c.put("line_no", r.lineNo);
            c.put("score", r.score);

            ObjectNode dn = c.putObject("dimensions");        // optional-actions / categorical ref
            for (Map.Entry<String, String> d : p.dimensions().entrySet()) dn.put(d.getKey(), d.getValue());

            if (p.verdict() != null) {
                c.put("verdict_code", p.verdict());
                c.put("outcome", p.verdict() == 0 ? "pass" : "fail");
            }
            ObjectNode on = c.putObject("objectives");
            for (GoalSpec g : goals)
                if (p.objectives().containsKey(g.key())) on.put(g.key(), p.objectives().get(g.key()));

            c.put("dominated_by", 0);                         // on the Pareto front -> dominated by none
            c.put("dominates", countDominated(p, cmp, goals));
            c.put("reason_non_dominated", reasonNonDominated(p, rows, goals));

            if (formal && !p.explicitId()) {
                ObjectNode iss = issues.addObject();
                boolean none = p.candidateId() == null;
                iss.put("level", none ? "error" : "warning");
                iss.put("line_no", r.lineNo);
                iss.put("candidate_id", p.candidateId());
                iss.put("message", none
                        ? "missing provenance: selected candidate has no explicit candidate_id and no "
                          + "dimensions to derive one — cannot trace it to a source/result row"
                        : "derived candidate_id from dimensions (no explicit candidate_id/combi_id token)");
            }
            // Formal studies must be attributable to a run — a selected candidate
            // with no run_id is an ERROR (the run that produced it is unknown).
            if (formal && (p.runId() == null || p.runId().isEmpty())) {
                ObjectNode iss = issues.addObject();
                iss.put("level", "error");
                iss.put("line_no", r.lineNo);
                iss.put("candidate_id", p.candidateId());
                iss.put("message", "missing run_id: a formal study requires every selected candidate to be "
                        + "attributable to a run (no run_id token on the metric line)");
            }
        }
        root.put("provenance_ok", !hasErrors(issues));
        return root;
    }

    // ── helpers ────────────────────────────────────────────────────────────
    private static boolean hasErrors(ArrayNode issues) {
        for (JsonNode n : issues) if ("error".equals(n.path("level").asText())) return true;
        return false;
    }

    private static double deviation(Provenance p, GoalSpec g) {
        Double v = p.objectives().get(g.key());
        return v == null ? WORST : g.deviation(v);
    }

    /** Count members of the bounded comparison set that this candidate strictly
     *  dominates (≤ on every objective, < on at least one). Self is excluded. */
    private static int countDominated(Provenance p, List<LineResult> cmp, List<GoalSpec> goals) {
        int n = 0;
        for (LineResult q : cmp) {
            Provenance pq = parse(q.originalLine, goals);
            if (pq.candidateId() != null && pq.candidateId().equals(p.candidateId())) continue;
            boolean allLe = true, oneLt = false;
            for (GoalSpec g : goals) {
                double a = deviation(p, g), b = deviation(pq, g);
                if (a > b) { allLe = false; break; }
                if (a < b) oneLt = true;
            }
            if (allLe && oneLt) n++;
        }
        return n;
    }

    /** Why is this candidate on the front? If it is the strict champion on some
     *  objective (best deviation among all front members), name that axis;
     *  otherwise it is an interior Pareto trade-off. Deterministic (goals order). */
    private static String reasonNonDominated(Provenance p, List<Map.Entry<LineResult, Provenance>> rows,
                                             List<GoalSpec> goals) {
        for (GoalSpec g : goals) {
            double mine = deviation(p, g);
            if (mine == WORST) continue;
            boolean strictBest = true;
            for (Map.Entry<LineResult, Provenance> e : rows) {
                Provenance other = e.getValue();
                if (other == p) continue;
                if (deviation(other, g) <= mine) { strictBest = false; break; }
            }
            if (strictBest) {
                Double val = p.objectives().get(g.key());
                return String.format(Locale.ROOT, "champion: strictly best %s (%s=%.4g) on the %d-point Pareto front",
                        g.mode().name().toLowerCase(Locale.ROOT) + " " + g.key(), g.key(), val, rows.size());
            }
        }
        return String.format(Locale.ROOT,
                "Pareto trade-off: not dominated by any of the %d front points (better than each on ≥1 objective)",
                rows.size());
    }
}
