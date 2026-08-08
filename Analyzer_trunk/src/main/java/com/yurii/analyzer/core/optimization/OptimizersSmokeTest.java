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

package com.yurii.analyzer.core.optimization;

import java.util.List;
import java.util.function.DoubleUnaryOperator;
import java.util.function.ToDoubleFunction;

/**
 * Run with:  mvn -q exec:java -Dexec.mainClass=com.yurii.analyzer.core.optimization.OptimizersSmokeTest
 *
 * Verifies each method against a known-answer problem and prints the residual
 * so the implementation can be audited without unit-test infrastructure.
 */
public final class OptimizersSmokeTest {
    private OptimizersSmokeTest() {}

    public static void main(String[] args) {
        int failures = 0;

        // ─── Brent: f(x) = (x - 3)^2 has its minimum at x* = 3, f(x*) = 0 ──
        Optimizers.Min1D b1 = Optimizers.brentMinimize(x -> (x - 3) * (x - 3), -10, 10, 1e-9, 200);
        failures += check("Brent (x-3)^2", b1.x(), 3.0, 1e-6);
        failures += check("Brent f(x*)",  b1.fx(), 0.0, 1e-12);

        // ─── Brent: smooth quartic, known textbook minimum ────────────────
        // f(x) = x^4 - 14*x^3 + 60*x^2 - 70*x  on [0,2] has its local min near x ≈ 0.7808
        DoubleUnaryOperator quartic = x -> x*x*x*x - 14*x*x*x + 60*x*x - 70*x;
        Optimizers.Min1D b2 = Optimizers.brentMinimize(quartic, 0, 2, 1e-9, 200);
        failures += check("Brent quartic x*", b2.x(), 0.78089, 1e-3);

        // ─── Newton-Raphson: root of x^2 - 2 from x0=1 → √2 ───────────────
        double sqrt2 = Optimizers.newtonRaphson(x -> x*x - 2, x -> 2*x, 1.0, 1e-12, 50);
        failures += check("Newton √2", sqrt2, Math.sqrt(2), 1e-10);

        // ─── Gradient descent: 2D quadratic → (1, 2) ──────────────────────
        Optimizers.MinND g = Optimizers.gradientDescent(
                v -> (v[0]-1)*(v[0]-1) + (v[1]-2)*(v[1]-2),
                new double[]{0, 0}, 0.1, 0.9, 500, 1e-9);
        failures += check("GD x[0]", g.x()[0], 1.0, 1e-3);
        failures += check("GD x[1]", g.x()[1], 2.0, 1e-3);

        // ─── Nelder-Mead: Rosenbrock → (1, 1) ─────────────────────────────
        Optimizers.MinND nm = Optimizers.nelderMead(
                v -> 100 * Math.pow(v[1] - v[0]*v[0], 2) + Math.pow(1 - v[0], 2),
                new double[]{-1.2, 1.0}, 0.1, 5000, 1e-10);
        failures += check("NM Rosenbrock x", nm.x()[0], 1.0, 1e-3);
        failures += check("NM Rosenbrock y", nm.x()[1], 1.0, 1e-3);

        // ─── Simulated annealing: same Rosenbrock landscape ───────────────
        Optimizers.MinND sa = Optimizers.simulatedAnnealing(
                v -> 100 * Math.pow(v[1] - v[0]*v[0], 2) + Math.pow(1 - v[0], 2),
                new double[]{-1.2, 1.0}, new double[]{0.5, 0.5}, 5.0, 0.999, 50_000, 42L);
        // SA is stochastic; tolerance is loose.
        failures += check("SA Rosenbrock f*", sa.fx(), 0.0, 0.5);

        // ─── Simpson ∫₀^π sin(x) dx = 2 ──────────────────────────────────
        double s = Optimizers.simpson(Math::sin, 0, Math.PI, 100);
        failures += check("Simpson ∫sin", s, 2.0, 1e-6);

        // ─── Trapezoidal ∫₀^1 x² dx = 1/3 ────────────────────────────────
        double t = Optimizers.trapezoidal(x -> x*x, 0, 1, 1000);
        failures += check("Trapezoid ∫x²", t, 1.0/3.0, 1e-4);

        // ─── RK4: y'(t)=y, y(0)=1 → y(1)=e ───────────────────────────────
        double[] yE = Optimizers.rk4((tt, y) -> new double[]{y[0]}, new double[]{1.0}, 0, 1, 0.01);
        failures += check("RK4 e^1", yE[0], Math.E, 1e-6);

        // ─── RK4: harmonic oscillator y'' = -y, y(0)=0, y'(0)=1 → y(π/2)=1
        double[] yH = Optimizers.rk4((tt, y) -> new double[]{y[1], -y[0]},
                new double[]{0.0, 1.0}, 0, Math.PI/2, 0.001);
        failures += check("RK4 sin(π/2)", yH[0], 1.0, 1e-5);
        failures += check("RK4 cos(π/2)", yH[1], 0.0, 1e-5);

        // ─── Pareto: hand-picked points ───────────────────────────────────
        // Minimize both objectives. Point (1, 5) dominates (2, 6); (3, 1) dominates none.
        // Expected front: { (1, 5), (3, 1) }. Point (2, 6) is dominated.
        List<double[]> pts = List.of(new double[]{1, 5}, new double[]{2, 6}, new double[]{3, 1});
        List<ToDoubleFunction<double[]>> objs = List.of(p -> p[0], p -> p[1]);
        List<double[]> front = Optimizers.paretoFront(pts, objs, List.of(true, true));
        failures += check("Pareto size", front.size(), 2);
        boolean has15 = front.stream().anyMatch(p -> p[0] == 1 && p[1] == 5);
        boolean has31 = front.stream().anyMatch(p -> p[0] == 3 && p[1] == 1);
        if (!(has15 && has31)) { System.out.println("✗ Pareto front contents wrong"); failures++; }

        // ─── ExprParser → Brent on parsed expression ──────────────────────
        DoubleUnaryOperator parsed = new ExprParser("x*x - 4*x + 5").compile();
        // f(x)=x²-4x+5 minimum at x=2, f=1
        failures += check("Parsed f(0)", parsed.applyAsDouble(0), 5.0, 1e-12);
        failures += check("Parsed f(2)", parsed.applyAsDouble(2), 1.0, 1e-12);
        Optimizers.Min1D bp = Optimizers.brentMinimize(parsed, -10, 10, 1e-9, 200);
        failures += check("Parsed+Brent x*", bp.x(), 2.0, 1e-6);
        failures += check("Parsed+Brent f*", bp.fx(), 1.0, 1e-12);

        // ─── ExprParser supports sin/cos/exp/sqrt/abs ─────────────────────
        DoubleUnaryOperator trig = new ExprParser("sin(x) + cos(x)").compile();
        // Maximum near x = π/4: sin+cos = √2 ≈ 1.41421
        // Minimize -f to find max via Brent
        Optimizers.Min1D bm = Optimizers.brentMinimize(x -> -trig.applyAsDouble(x), 0, Math.PI, 1e-9, 200);
        failures += check("Brent on sin+cos x*", bm.x(), Math.PI/4, 1e-4);

        // ─── ODE: confidence model dC/dn = (1 - C)/100, C(0) = 0.5 ────────
        // Analytical solution: C(n) = 1 - 0.5·exp(-n/100) ≡ 0.5 + 0.5·(1 - exp(-n/100))
        // Verify legacy formula is in fact the closed-form solution.
        double n = 200;
        double[] cNumeric = Optimizers.rk4(
                (tt, y) -> new double[]{(1.0 - y[0]) / 100.0},
                new double[]{0.5}, 0, n, 0.1);
        double cAnalytical = 0.5 + 0.5 * (1.0 - Math.exp(-n / 100.0));
        failures += check("Confidence ODE residual", cNumeric[0], cAnalytical, 1e-6);

        System.out.println();
        if (failures == 0) System.out.println("ALL OPTIMIZATION CHECKS PASSED");
        else { System.out.println(failures + " CHECK(S) FAILED"); System.exit(1); }
    }

    private static int check(String name, double got, double want, double tol) {
        boolean ok = Math.abs(got - want) <= tol;
        System.out.printf("%s %-30s got=%.10g  want=%.10g  Δ=%.3g%n",
                ok ? "✓" : "✗", name, got, want, Math.abs(got - want));
        return ok ? 0 : 1;
    }

    private static int check(String name, int got, int want) {
        boolean ok = got == want;
        System.out.printf("%s %-30s got=%d  want=%d%n", ok ? "✓" : "✗", name, got, want);
        return ok ? 0 : 1;
    }
}
