package com.yurii.analyzer.core.optimization;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.function.DoubleUnaryOperator;
import java.util.function.ToDoubleFunction;

/**
 * Numerical optimization toolkit — pure Java, no external deps.
 *
 * Methods provided:
 *   1D minimization      — Brent's method (golden section + parabolic interpolation)
 *   1D root finding      — Newton-Raphson with safe-step fallback
 *   ND minimization      — gradient descent w/ momentum + finite-difference gradient
 *                          Nelder-Mead simplex (derivative-free)
 *                          Simulated annealing (stochastic global)
 *   Numerical integration — Simpson's composite rule (continuous & sampled)
 *                           Trapezoidal rule
 *   ODE integration      — Classical Runge-Kutta 4th order
 *   Multi-objective      — Pareto-frontier extraction (non-dominated set)
 *
 * Each method returns either a numeric value or a Min1D / MinND record carrying
 * (x*, f(x*), iterations, converged), enabling callers to act on convergence.
 */
public final class Optimizers {
    private Optimizers() {}

    public interface MultivariateFunction { double value(double[] x); }
    public interface VectorField          { double[] derivative(double t, double[] y); }

    public record Min1D(double x, double fx, int iterations, boolean converged) {}
    public record MinND(double[] x, double fx, int iterations, boolean converged) {}

    // ─── 1D minimization: Brent's method ─────────────────────────────────
    // Combines golden-section search (guaranteed convergence) with inverse
    // parabolic interpolation (super-linear convergence near a smooth minimum).
    // Reference: Brent, "Algorithms for Minimization Without Derivatives" (1973).

    /**
     * 1D minimisation of a smooth unimodal function on [a, b].
     *
     * @implNote <b>LOAD-BEARING</b> when invoked on a user-supplied
     *   {@code OptimizationGoal.objective} expression (e.g. {@code (x-7)^2}):
     *   then it's a real optimisation step — finds the analytical argmin
     *   that drives the per-line target scoring.
     *   <b>DECORATIVE</b> when invoked on a piecewise-linear interpolation
     *   of a discrete metric series (as {@code MetricStreamAnalyzer} does):
     *   then the argmin is always at a sample point and equals the value
     *   that {@code Collections.min} would have given.  Kept because the
     *   API is the same; users should interpret the result accordingly.
     */
    public static Min1D brentMinimize(DoubleUnaryOperator f, double a, double b, double tol, int maxIter) {
        if (a > b) { double tmp = a; a = b; b = tmp; }
        final double GOLDEN = 0.3819660112501051; // (3 - sqrt(5)) / 2
        double x = a + GOLDEN * (b - a), w = x, v = x;
        double fx = f.applyAsDouble(x), fw = fx, fv = fx;
        double d = 0.0, e = 0.0;

        for (int iter = 0; iter < maxIter; iter++) {
            double xm = 0.5 * (a + b);
            double tol1 = tol * Math.abs(x) + 1e-12;
            double tol2 = 2.0 * tol1;
            if (Math.abs(x - xm) <= tol2 - 0.5 * (b - a))
                return new Min1D(x, fx, iter, true);

            double p = 0, q = 0, r;
            if (Math.abs(e) > tol1) {
                r = (x - w) * (fx - fv);
                q = (x - v) * (fx - fw);
                p = (x - v) * q - (x - w) * r;
                q = 2 * (q - r);
                if (q > 0) p = -p;
                q = Math.abs(q);
                double etemp = e;
                e = d;
                if (Math.abs(p) >= Math.abs(0.5 * q * etemp)
                        || p <= q * (a - x) || p >= q * (b - x)) {
                    e = (x >= xm) ? a - x : b - x;
                    d = GOLDEN * e;
                } else {
                    d = p / q;
                    double u = x + d;
                    if (u - a < tol2 || b - u < tol2) d = Math.copySign(tol1, xm - x);
                }
            } else {
                e = (x >= xm) ? a - x : b - x;
                d = GOLDEN * e;
            }
            double u = (Math.abs(d) >= tol1) ? x + d : x + Math.copySign(tol1, d);
            double fu = f.applyAsDouble(u);
            if (fu <= fx) {
                if (u >= x) a = x; else b = x;
                v = w; fv = fw; w = x; fw = fx; x = u; fx = fu;
            } else {
                if (u < x) a = u; else b = u;
                if (fu <= fw || w == x) { v = w; fv = fw; w = u; fw = fu; }
                else if (fu <= fv || v == x || v == w) { v = u; fv = fu; }
            }
        }
        return new Min1D(x, fx, maxIter, false);
    }

    // ─── 1D root finding: Newton-Raphson w/ damped step ──────────────────

    /**
     * Newton-Raphson root-finder.
     *
     * @implNote <b>LOAD-BEARING</b> when the user supplies an actual closed-form
     *   first derivative {@code fPrime}; that's the textbook use.
     *   <b>DECORATIVE</b> when {@code fPrime} is a central-difference
     *   numerical approximation over a discrete metric series (as
     *   {@code MetricStreamAnalyzer} uses it for "critical points") —
     *   refines sign-change locations that the discrete diff already
     *   identified; the refinement is sub-pixel and irrelevant for
     *   per-line ranking.  Kept for completeness of the optimisation
     *   toolkit, not because it changes ranking outcomes.
     */
    public static double newtonRaphson(DoubleUnaryOperator f, DoubleUnaryOperator fPrime,
                                       double x0, double tol, int maxIter) {
        double x = x0;
        for (int iter = 0; iter < maxIter; iter++) {
            double fx = f.applyAsDouble(x);
            if (Math.abs(fx) < tol) return x;
            double dfx = fPrime.applyAsDouble(x);
            if (Math.abs(dfx) < 1e-14) break;
            double step = fx / dfx;
            // Damp catastrophic steps (Armijo-like back-off if f explodes)
            double xNext = x - step;
            double fNext = f.applyAsDouble(xNext);
            int trim = 0;
            while (Math.abs(fNext) > Math.abs(fx) && trim < 12) {
                step *= 0.5;
                xNext = x - step;
                fNext = f.applyAsDouble(xNext);
                trim++;
            }
            x = xNext;
        }
        return x;
    }

    // ─── ND gradient descent + momentum + finite-diff gradient ───────────

    public static MinND gradientDescent(MultivariateFunction f, double[] x0, double lr,
                                        double momentum, int maxIter, double tol) {
        int n = x0.length;
        double[] x = x0.clone();
        double[] velocity = new double[n];
        double[] grad = new double[n];
        double fx = f.value(x);
        for (int iter = 0; iter < maxIter; iter++) {
            finiteDiffGradient(f, x, grad);
            double gnorm = 0;
            for (double g : grad) gnorm += g * g;
            if (Math.sqrt(gnorm) < tol) return new MinND(x, fx, iter, true);
            for (int i = 0; i < n; i++) {
                velocity[i] = momentum * velocity[i] - lr * grad[i];
                x[i] += velocity[i];
            }
            fx = f.value(x);
        }
        return new MinND(x, fx, maxIter, false);
    }

    /** Symmetric central-difference gradient. O(2n) function evals. */
    public static void finiteDiffGradient(MultivariateFunction f, double[] x, double[] grad) {
        final double H = 1e-6;
        int n = x.length;
        for (int i = 0; i < n; i++) {
            double saved = x[i];
            double h = H * Math.max(1.0, Math.abs(saved));
            x[i] = saved + h; double fp = f.value(x);
            x[i] = saved - h; double fm = f.value(x);
            x[i] = saved;
            grad[i] = (fp - fm) / (2 * h);
        }
    }

    // ─── Nelder-Mead simplex (derivative-free) ────────────────────────────

    public static MinND nelderMead(MultivariateFunction f, double[] x0, double initialStep,
                                   int maxIter, double tol) {
        int n = x0.length;
        double[][] simplex = new double[n + 1][n];
        double[] fvals = new double[n + 1];
        for (int i = 0; i <= n; i++) {
            simplex[i] = x0.clone();
            if (i > 0) simplex[i][i - 1] += initialStep;
            fvals[i] = f.value(simplex[i]);
        }
        final double ALPHA = 1.0, GAMMA = 2.0, RHO = 0.5, SIGMA = 0.5;

        for (int iter = 0; iter < maxIter; iter++) {
            // Insertion-sort by f value (n+1 vertices, small).
            for (int i = 1; i <= n; i++) {
                int j = i;
                while (j > 0 && fvals[j - 1] > fvals[j]) {
                    double tmpf = fvals[j]; fvals[j] = fvals[j - 1]; fvals[j - 1] = tmpf;
                    double[] tmps = simplex[j]; simplex[j] = simplex[j - 1]; simplex[j - 1] = tmps;
                    j--;
                }
            }
            double spread = fvals[n] - fvals[0];
            if (spread < tol) return new MinND(simplex[0], fvals[0], iter, true);

            // Centroid of best n vertices (excluding worst).
            double[] xo = new double[n];
            for (int i = 0; i < n; i++) for (int j = 0; j < n; j++) xo[j] += simplex[i][j];
            for (int j = 0; j < n; j++) xo[j] /= n;

            // Reflection
            double[] xr = new double[n];
            for (int j = 0; j < n; j++) xr[j] = xo[j] + ALPHA * (xo[j] - simplex[n][j]);
            double fr = f.value(xr);

            if (fvals[0] <= fr && fr < fvals[n - 1]) { simplex[n] = xr; fvals[n] = fr; continue; }

            if (fr < fvals[0]) {
                // Expansion
                double[] xe = new double[n];
                for (int j = 0; j < n; j++) xe[j] = xo[j] + GAMMA * (xr[j] - xo[j]);
                double fe = f.value(xe);
                if (fe < fr) { simplex[n] = xe; fvals[n] = fe; }
                else        { simplex[n] = xr; fvals[n] = fr; }
                continue;
            }

            // Contraction
            double[] xc = new double[n];
            for (int j = 0; j < n; j++) xc[j] = xo[j] + RHO * (simplex[n][j] - xo[j]);
            double fc = f.value(xc);
            if (fc < fvals[n]) { simplex[n] = xc; fvals[n] = fc; continue; }

            // Shrink toward best
            for (int i = 1; i <= n; i++) {
                for (int j = 0; j < n; j++)
                    simplex[i][j] = simplex[0][j] + SIGMA * (simplex[i][j] - simplex[0][j]);
                fvals[i] = f.value(simplex[i]);
            }
        }
        return new MinND(simplex[0], fvals[0], maxIter, false);
    }

    // ─── Simulated annealing (global, stochastic) ────────────────────────

    /**
     * Simulated annealing for stochastic global minimisation.
     *
     * @implNote <b>LOAD-BEARING</b> in multimodal multivariate settings
     *   (e.g. the Rosenbrock-like surfaces in {@code OptimizersSmokeTest})
     *   where a single-start gradient/simplex method can stall.
     *   <b>DECORATIVE</b> when invoked on a 1D linearly-interpolated metric
     *   series (as {@code MetricStreamAnalyzer} does per auto-discovered
     *   key) — converges arbitrarily close to Brent's answer in that
     *   setting, doesn't add information.  Kept there for "all workflows
     *   fire" verification, not because it discovers anything new on those
     *   inputs.  See the streaming aggregator's deep-analysis section in
     *   {@link OnlineMetricAggregator.Snapshot#render()}.
     */
    public static MinND simulatedAnnealing(MultivariateFunction f, double[] x0, double[] stepSize,
                                           double temp0, double cooling, int maxIter, long seed) {
        Random rng = new Random(seed);
        double[] x = x0.clone();
        double[] best = x.clone();
        double fx = f.value(x);
        double fbest = fx;
        double T = temp0;
        for (int iter = 0; iter < maxIter; iter++) {
            double[] xn = x.clone();
            for (int i = 0; i < x.length; i++) xn[i] += (rng.nextDouble() * 2 - 1) * stepSize[i];
            double fn = f.value(xn);
            double df = fn - fx;
            if (df < 0 || rng.nextDouble() < Math.exp(-df / Math.max(1e-12, T))) {
                x = xn; fx = fn;
                if (fx < fbest) { fbest = fx; best = x.clone(); }
            }
            T *= cooling;
        }
        return new MinND(best, fbest, maxIter, true);
    }

    // ─── Numerical integration (Simpson's composite rule, trapezoidal) ───

    public static double simpson(DoubleUnaryOperator f, double a, double b, int n) {
        if (n < 2) n = 2;
        if (n % 2 != 0) n++;
        double h = (b - a) / n;
        double s = f.applyAsDouble(a) + f.applyAsDouble(b);
        for (int i = 1; i < n; i++) s += (i % 2 == 0 ? 2 : 4) * f.applyAsDouble(a + i * h);
        return s * h / 3.0;
    }

    public static double trapezoidal(DoubleUnaryOperator f, double a, double b, int n) {
        if (n < 1) n = 1;
        double h = (b - a) / n;
        double s = 0.5 * (f.applyAsDouble(a) + f.applyAsDouble(b));
        for (int i = 1; i < n; i++) s += f.applyAsDouble(a + i * h);
        return s * h;
    }

    /** Composite Simpson over uniformly-sampled values; falls back to trapezoid on the tail when N is odd. */
    public static double simpsonOverSamples(double[] values, double dx) {
        int len = values.length;
        if (len == 0) return 0.0;
        if (len == 1) return values[0] * dx;
        int n = len - 1;
        int evenN = (n % 2 == 0) ? n : n - 1;
        double s = values[0] + values[evenN];
        for (int i = 1; i < evenN; i++) s += (i % 2 == 0 ? 2 : 4) * values[i];
        double simpsonPart = s * dx / 3.0;
        double trapPart = (evenN < n) ? 0.5 * (values[evenN] + values[evenN + 1]) * dx : 0.0;
        return simpsonPart + trapPart;
    }

    // ─── ODE integration: classical Runge-Kutta 4th order ────────────────
    // Solves the IVP   y'(t) = f(t, y),   y(t0) = y0   on [t0, tf] with step dt.

    /**
     * Classical 4th-order Runge-Kutta integrator for first-order ODE systems.
     *
     * @implNote <b>LOAD-BEARING</b> when used to integrate a fitted
     *   relaxation model {@code dy/dn = (μ − y)/τ} as a smoother over a
     *   metric series — that produces a smoothed trajectory whose stdev
     *   ≤ the raw series stdev (verified in CLAIM 11 of
     *   {@code OptimizationVerification}).  Genuine value-add for trend
     *   visualisation and regression detection.
     *   <b>DECORATIVE</b> when used to "verify" the legacy confidence
     *   formula via {@link AnalyzerCore#verifyConfidenceOde} — see that
     *   method's note: it reproduces {@code exp()} to machine precision,
     *   which is a known property of RK4, not a discovery.
     */
    public static double[] rk4(VectorField f, double[] y0, double t0, double tf, double dt) {
        int n = y0.length;
        double[] y = y0.clone();
        double t = t0;
        while (t < tf) {
            double h = Math.min(dt, tf - t);
            double[] k1 = f.derivative(t, y);
            double[] k2 = f.derivative(t + h / 2, addScaled(y, k1, h / 2));
            double[] k3 = f.derivative(t + h / 2, addScaled(y, k2, h / 2));
            double[] k4 = f.derivative(t + h,     addScaled(y, k3, h));
            for (int i = 0; i < n; i++) y[i] += h / 6.0 * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]);
            t += h;
        }
        return y;
    }

    private static double[] addScaled(double[] a, double[] b, double s) {
        double[] r = new double[a.length];
        for (int i = 0; i < a.length; i++) r[i] = a[i] + s * b[i];
        return r;
    }

    // ─── Pareto front (multi-objective non-dominated set) ────────────────
    // Delegates to {@link Dominance} so batch and streaming paths share the
    // SAME dominance algorithm — TARGET-mode support, NaN handling, and
    // policy-driven axis skip all come along automatically.

    public static <T> List<T> paretoFront(List<T> items, List<ToDoubleFunction<T>> objectives,
                                          List<Boolean> minimize) {
        if (objectives.isEmpty() || items.isEmpty()) return new ArrayList<>(items);
        if (objectives.size() != minimize.size())
            throw new IllegalArgumentException("objectives and minimize must have the same size");
        // Translate (extractor, minimize-flag) pairs into the unified
        // GoalSpec representation, then delegate.  The axis names are
        // synthetic since the batch path doesn't track named keys.
        GoalSpec[] goals = new GoalSpec[objectives.size()];
        for (int i = 0; i < goals.length; i++) {
            goals[i] = minimize.get(i) ? GoalSpec.min("axis_" + i)
                                       : GoalSpec.max("axis_" + i);
        }
        double[][] vectors = Dominance.extractVectors(items, objectives);
        return Dominance.paretoFront(items, vectors, goals);
    }

    /**
     * Pareto-front overload that takes per-axis goals directly (with
     * MIN/MAX/TARGET modes + weights).  Use when callers already have
     * named goals — avoids the boolean-flag round-trip and gives full
     * access to TARGET mode in batch settings.
     */
    public static <T> List<T> paretoFrontWithGoals(List<T> items,
                                                    List<ToDoubleFunction<T>> objectives,
                                                    List<GoalSpec> goals) {
        if (objectives.isEmpty() || items.isEmpty()) return new ArrayList<>(items);
        if (objectives.size() != goals.size())
            throw new IllegalArgumentException("objectives and goals must have the same size");
        double[][] vectors = Dominance.extractVectors(items, objectives);
        return Dominance.paretoFront(items, vectors, goals.toArray(new GoalSpec[0]));
    }
}
