package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.AnalyzerCore;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.Set;

/**
 * Repeat-aware observation aggregation. The executor persists raw observations; this
 * class validates their identity/provenance and produces one objective vector per
 * candidate before Pareto ranking.
 */
public final class RepeatAggregator {
    private RepeatAggregator() {}

    private static final Set<String> NON_METRIC_KEYS = Set.of(
            "candidate_id", "repeat_idx", "env_id", "source_ref", "run_id",
            "FW_VAR", "FW_CUSTOM_VAR");

    public static final double DEFAULT_ALPHA = 0.05;
    public static final int MAX_EXACT_N = 1024;

    public record SampleIdentity(String candidateId, int repeatIdx, String envId) {}

    public record Sample(SampleIdentity identity, String sourceRef, String runId,
                         Integer verdict, Map<String, Double> metrics) {}

    public record MetricStat(double median, double ciLow, double ciHigh, boolean ciValid,
                             int n, String method, double coverage) {}

    public record CandidateAggregate(String candidateId, String envId, String sourceRef,
                                     String runId, Integer verdict, int sampleCount,
                                     int missingTotal, Map<String, Double> medianRaw,
                                     Map<String, MetricStat> objective) {}

    public record EligibilityResult(List<String> eligibleLines, int rejectedNonzero,
                                    int missingVerdict) {
        public EligibilityResult {
            eligibleLines = List.copyOf(eligibleLines);
        }
    }

    public static boolean containsRepeatIdentity(List<String> corpusLines) {
        for (String line : corpusLines) {
            if (line != null && Arrays.stream(line.trim().split("\\s+"))
                    .anyMatch(token -> token.startsWith("repeat_idx="))) return true;
        }
        return false;
    }

    /**
     * Retain candidates with an explicit zero verdict and legacy candidates with no verdict.
     * Explicit non-zero verdicts are execution/test failures and must never enter optimization.
     */
    public static EligibilityResult filterEligible(List<String> analyzerLines) {
        Objects.requireNonNull(analyzerLines, "analyzerLines");
        List<String> eligible = new ArrayList<>();
        int rejected = 0;
        int missing = 0;
        for (String line : analyzerLines) {
            Integer verdict = explicitVerdict(line);
            if (verdict == null) {
                missing++;
                eligible.add(line);
            } else if (verdict == 0) {
                eligible.add(line);
            } else {
                rejected++;
            }
        }
        if (eligible.isEmpty())
            throw new IllegalArgumentException(
                    "no eligible candidates remain after excluding " + rejected
                            + " explicit nonzero FW_VAR candidate(s)");
        return new EligibilityResult(eligible, rejected, missing);
    }

    private static Integer explicitVerdict(String line) {
        if (line == null)
            throw new IllegalArgumentException("candidate line must not be null");
        Integer verdict = null;
        boolean seen = false;
        for (String token : line.trim().split("\\s+")) {
            int equals = token.indexOf('=');
            if (equals <= 0 || !token.substring(0, equals).equals("FW_VAR")) continue;
            Integer parsed;
            try {
                parsed = Integer.valueOf(token.substring(equals + 1));
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "invalid FW_VAR '" + token.substring(equals + 1) + "'", ex);
            }
            if (seen && !Objects.equals(verdict, parsed))
                throw new IllegalArgumentException(
                        "conflicting FW_VAR tokens in candidate line: " + line);
            verdict = parsed;
            seen = true;
        }
        return verdict;
    }

    /** Parse one raw observation. Invalid explicit identity fails closed. */
    public static Sample parseLine(String line) {
        if (line == null || line.isBlank()) return null;
        String candidateId = null;
        String envId = "";
        String sourceRef = null;
        String runId = null;
        Integer verdict = null;
        int repeatIdx = 0;
        boolean repeatSeen = false;
        Map<String, Double> metrics = new LinkedHashMap<>();

        for (String token : line.trim().split("\\s+")) {
            int equals = token.indexOf('=');
            if (equals <= 0) continue;
            String key = token.substring(0, equals);
            String value = token.substring(equals + 1);
            switch (key) {
                case "candidate_id" -> candidateId = value;
                case "env_id" -> envId = value;
                case "source_ref" -> sourceRef = value;
                case "run_id" -> runId = value;
                case "repeat_idx" -> {
                    repeatSeen = true;
                    try {
                        repeatIdx = Integer.parseInt(value);
                    } catch (NumberFormatException ex) {
                        throw new IllegalArgumentException(
                                "invalid repeat_idx '" + value + "' in: " + line, ex);
                    }
                    if (repeatIdx < 0)
                        throw new IllegalArgumentException("repeat_idx must be >= 0 in: " + line);
                }
                case "FW_VAR" -> {
                    try { verdict = Integer.valueOf(value); }
                    catch (NumberFormatException ex) {
                        throw new IllegalArgumentException("invalid FW_VAR '" + value + "'", ex);
                    }
                }
                case "FW_CUSTOM_VAR" -> { /* verdict projection uses FW_VAR */ }
                default -> {
                    if (NON_METRIC_KEYS.contains(key)) continue;
                    OptionalDouble parsed = AnalyzerCore.tryParseNumeric(value);
                    if (parsed.isPresent() && Double.isFinite(parsed.getAsDouble()))
                        metrics.put(key, parsed.getAsDouble());
                }
            }
        }

        if (candidateId == null) {
            if (repeatSeen)
                throw new IllegalArgumentException(
                        "repeat-aware observation is missing candidate_id: " + line);
            return null;
        }
        if (candidateId.isBlank())
            throw new IllegalArgumentException("candidate_id must be non-empty: " + line);
        return new Sample(new SampleIdentity(candidateId, repeatIdx, envId),
                sourceRef, runId, verdict, Map.copyOf(metrics));
    }

    public static Map<String, CandidateAggregate> aggregate(
            List<String> corpusLines, List<GoalSpec> goals, double alpha) {
        validateAlpha(alpha);
        Objects.requireNonNull(corpusLines, "corpusLines");
        Objects.requireNonNull(goals, "goals");

        Map<SampleIdentity, Sample> deduped = new LinkedHashMap<>();
        for (String line : corpusLines) {
            Sample sample = parseLine(line);
            if (sample == null) continue;
            Sample prior = deduped.putIfAbsent(sample.identity(), sample);
            if (prior != null && !prior.equals(sample))
                throw new IllegalArgumentException(
                        "conflicting duplicate sample identity " + sample.identity());
        }

        Map<String, List<Sample>> grouped = new LinkedHashMap<>();
        for (Sample sample : deduped.values())
            grouped.computeIfAbsent(sample.identity().candidateId(), ignored -> new ArrayList<>())
                    .add(sample);

        Map<String, CandidateAggregate> result = new LinkedHashMap<>();
        for (Map.Entry<String, List<Sample>> entry : grouped.entrySet()) {
            List<Sample> samples = entry.getValue();
            Sample first = samples.get(0);
            for (Sample sample : samples) {
                requireSame("env_id", first.identity().envId(), sample.identity().envId(), entry.getKey());
                requireSame("run_id", first.runId(), sample.runId(), entry.getKey());
                requireSame("source_ref", first.sourceRef(), sample.sourceRef(), entry.getKey());
                requireSame("FW_VAR", first.verdict(), sample.verdict(), entry.getKey());
            }

            Map<String, Double> medianRaw = new LinkedHashMap<>();
            Map<String, MetricStat> objective = new LinkedHashMap<>();
            int missingTotal = 0;
            for (GoalSpec goal : goals) {
                List<Double> raw = new ArrayList<>();
                for (Sample sample : samples) {
                    Double value = sample.metrics().get(goal.key());
                    if (value != null) raw.add(value);
                }
                missingTotal += samples.size() - raw.size();
                if (raw.isEmpty()) continue;
                double[] rawValues = raw.stream().mapToDouble(Double::doubleValue).toArray();
                double[] sortedRaw = rawValues.clone();
                Arrays.sort(sortedRaw);
                medianRaw.put(goal.key(), median(sortedRaw));
                double[] deviations = raw.stream().mapToDouble(goal::deviation).toArray();
                objective.put(goal.key(), orderStatisticCI(deviations, alpha));
            }

            result.put(entry.getKey(), new CandidateAggregate(
                    entry.getKey(), first.identity().envId(), first.sourceRef(), first.runId(),
                    first.verdict(), samples.size(), missingTotal,
                    Map.copyOf(medianRaw), Map.copyOf(objective)));
        }
        return result;
    }

    public static Map<String, CandidateAggregate> aggregate(
            List<String> corpusLines, List<GoalSpec> goals) {
        return aggregate(corpusLines, goals, DEFAULT_ALPHA);
    }

    /**
     * Convert candidate aggregates to ordinary Analyzer lines. Values are chosen so applying
     * the original GoalSpec deviation yields the aggregate objective: raw median for MIN/MAX,
     * and target+medianDeviation for TARGET.
     */
    public static List<String> toAnalyzerLines(
            Map<String, CandidateAggregate> aggregates, List<GoalSpec> goals) {
        List<String> lines = new ArrayList<>();
        for (CandidateAggregate aggregate : aggregates.values()) {
            StringBuilder line = new StringBuilder();
            appendToken(line, "candidate_id", aggregate.candidateId());
            if (aggregate.sourceRef() != null)
                appendToken(line, "source_ref", aggregate.sourceRef());
            if (aggregate.runId() != null)
                appendToken(line, "run_id", aggregate.runId());
            if (aggregate.verdict() != null)
                appendToken(line, "FW_VAR", aggregate.verdict());
            for (GoalSpec goal : goals) {
                MetricStat stat = aggregate.objective().get(goal.key());
                if (stat == null) continue;
                double value = switch (goal.mode()) {
                    case MINIMIZE -> stat.median();
                    case MAXIMIZE -> -stat.median();
                    case TARGET -> goal.targetValue() + stat.median();
                };
                appendToken(line, goal.key(), String.format(Locale.ROOT, "%.17g", value));
            }
            lines.add(line.toString());
        }
        return lines;
    }

    private static void appendToken(StringBuilder line, String key, Object value) {
        if (line.length() > 0) line.append(' ');
        line.append(key).append('=').append(String.valueOf(value).replace(' ', '_'));
    }

    private static void requireSame(String field, Object expected, Object actual, String candidateId) {
        if (!Objects.equals(expected, actual))
            throw new IllegalArgumentException(
                    "candidate " + candidateId + " has inconsistent " + field
                            + ": " + expected + " vs " + actual);
    }

    public static double median(double[] sorted) {
        if (sorted == null || sorted.length == 0)
            throw new IllegalArgumentException("median requires at least one value");
        int n = sorted.length;
        return n % 2 == 1
                ? sorted[n / 2]
                : (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0;
    }

    public static MetricStat orderStatisticCI(double[] values, double alpha) {
        validateAlpha(alpha);
        if (values == null || values.length == 0)
            throw new IllegalArgumentException("orderStatisticCI requires at least one value");
        double[] sorted = values.clone();
        for (double value : sorted)
            if (!Double.isFinite(value))
                throw new IllegalArgumentException("orderStatisticCI requires finite values");
        Arrays.sort(sorted);

        int n = sorted.length;
        double med = median(sorted);
        if (n == 1)
            return new MetricStat(med, sorted[0], sorted[0], false, 1, "point_k1", Double.NaN);
        if (n > MAX_EXACT_N)
            return new MetricStat(med, sorted[0], sorted[n - 1], false, n,
                    "exceeds_exact_bound", Double.NaN);

        double halfAlpha = alpha / 2.0;
        double term = Math.pow(0.5, n);
        double cumulative = 0.0;
        int lowerRank = 0;
        for (int i = 0; i < n; i++) {
            if (cumulative + term > halfAlpha) break;
            cumulative += term;
            lowerRank = i + 1;
            term = term * (double) (n - i) / (double) (i + 1);
        }
        if (lowerRank == 0)
            return new MetricStat(med, sorted[0], sorted[n - 1], false, n,
                    "range_insufficient_n", Double.NaN);

        int upperRank = n + 1 - lowerRank;
        double coverage = 1.0 - 2.0 * cumulative;
        return new MetricStat(med, sorted[lowerRank - 1], sorted[upperRank - 1],
                true, n, "order_statistic", coverage);
    }

    private static void validateAlpha(double alpha) {
        if (!Double.isFinite(alpha) || alpha <= 0.0 || alpha >= 1.0)
            throw new IllegalArgumentException("alpha must be finite and in (0,1)");
    }

    public static Map<String, Set<String>> tieNeighborhoods(
            Map<String, CandidateAggregate> aggregates, List<GoalSpec> goals) {
        List<String> ids = new ArrayList<>(aggregates.keySet());
        Map<String, Set<String>> neighborhoods = new LinkedHashMap<>();
        for (String left : ids) {
            Set<String> neighbors = new LinkedHashSet<>();
            neighbors.add(left);
            for (String right : ids) {
                if (!left.equals(right)
                        && noiseTied(aggregates.get(left), aggregates.get(right), goals))
                    neighbors.add(right);
            }
            neighborhoods.put(left, neighbors);
        }
        return neighborhoods;
    }

    private static boolean noiseTied(
            CandidateAggregate left, CandidateAggregate right, List<GoalSpec> goals) {
        for (GoalSpec goal : goals) {
            MetricStat a = left.objective().get(goal.key());
            MetricStat b = right.objective().get(goal.key());
            if (a == null || b == null || !a.ciValid() || !b.ciValid()) return false;
            if (Math.max(a.ciLow(), b.ciLow()) > Math.min(a.ciHigh(), b.ciHigh()))
                return false;
        }
        return true;
    }
}
