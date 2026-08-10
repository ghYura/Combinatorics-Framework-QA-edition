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
// Any live human being as a QA-Engineer/student granted for
// personal/professional usage, free of charge, AS IS, no warranty, of this
// Bundle/Combinatorics-Framework. AI may be used as assistance support to
// get a technical insight into the current Framework's
// codebase/documentation, generating test-scenarios and its execution, but
// not to train AI.
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.yurii.analyzer.core;

import com.fasterxml.jackson.databind.JsonNode;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Python-side scipy-optimize bridge used by {@code OptimizationAnalyzer} when
 * a line carries a {@code key = expr; key = expr; ...} payload.  Each
 * line is shipped to a tiny bundled Python script (auto-extracted to
 * {@code /tmp/yurii_universal_opt.py} on first call) which evaluates the
 * payload's pseudo-Python statements, identifies a callable {@code objective}
 * if one was declared, and runs {@code scipy.optimize.minimize}.  The
 * returned key/values are merged into the line's {@code kvPairs}.
 *
 * Decomposed from {@code AnalyzerCore.UniversalDynamicOptimizer} (was a
 * nested static class) so the 2200-line AnalyzerCore stays readable.  Public
 * API is unchanged — callers reference {@code UniversalDynamicOptimizer} in
 * the same package without import changes.
 *
 * Singleton-style scipy probe (cached after first call), thread-safe via
 * the {@code SCRIPT_LOCK} object.
 *
 * Security note (consistent with the project's honest disclosure): scipy
 * runs with {@code __builtins__} blanked but {@code eval()} on input is
 * still not a real sandbox.  Only enable for trusted inputs.
 */
public final class UniversalDynamicOptimizer {
    private UniversalDynamicOptimizer() {}

    private static volatile Path SCRIPT_PATH;
    private static volatile Boolean SCIPY_AVAILABLE;
    private static final Object SCRIPT_LOCK = new Object();

    private static final String SCRIPT_BODY =
            "import sys, json\n" +
            "try:\n" +
            "    import scipy.optimize as opt\n" +
            "    has_scipy = True\n" +
            "except ImportError:\n" +
            "    has_scipy = False\n" +
            "payload = sys.argv[1] if len(sys.argv) > 1 else ''\n" +
            "parts = [p.strip() for p in payload.split(';') if p.strip()]\n" +
            "env = {}\n" +
            "obj = None\n" +
            "for p in parts:\n" +
            "    if '=' not in p: continue\n" +
            "    k, v = p.split('=', 1)\n" +
            "    k, v = k.strip(), v.strip()\n" +
            "    try:\n" +
            "        val = eval(v, {'__builtins__': {}}, env)\n" +
            "        env[k] = val\n" +
            "        if callable(val) and ('lambda' in v or k in ['objective','func','loss_func','target']):\n" +
            "            obj = val\n" +
            "    except Exception:\n" +
            "        pass\n" +
            "out = {}\n" +
            "for k, v in env.items():\n" +
            "    if not callable(v): out[k] = str(v)\n" +
            "if obj and has_scipy:\n" +
            "    try:\n" +
            "        x0 = env.get('params', {}).get('start_point', [0.0]) if isinstance(env.get('params'), dict) else [0.0]\n" +
            "        if not isinstance(x0, list): x0 = [x0]\n" +
            "        res = opt.minimize(obj, x0)\n" +
            "        out['python_opt_val'] = str(res.fun)\n" +
            "        out['python_opt_success'] = str(res.success)\n" +
            "    except Exception as e:\n" +
            "        out['python_opt_err'] = str(e)\n" +
            "print(json.dumps(out))\n";

    public static Map<String, String> evaluate(String payload) {
        Map<String, String> result = new LinkedHashMap<>();
        if (payload == null || !payload.contains("=")) return result;
        try {
            Path script = ensureScript();
            String pyCmd = pythonExecutable();
            if (Boolean.FALSE.equals(SCIPY_AVAILABLE)) {
                // Skip scipy-dependent invocation; still allow eval-based parse.
            }
            ProcessBuilder pb = new ProcessBuilder(pyCmd, script.toAbsolutePath().toString(), payload);
            pb.redirectErrorStream(true);
            Process p = pb.start();
            boolean finished = p.waitFor(10, TimeUnit.SECONDS);
            if (!finished) {
                p.descendants().forEach(ProcessHandle::destroyForcibly);
                p.destroyForcibly();
                result.put("python_eval_error", "timeout");
                return result;
            }
            String out = readAll(p.getInputStream());
            JsonNode node = AnalyzerCore.mapper().readTree(out);
            if (node.isObject()) {
                for (Map.Entry<String, JsonNode> e : node.properties())
                    result.put(e.getKey(), e.getValue().asText());
            }
        } catch (Exception e) {
            result.put("python_eval_error", e.getMessage());
        }
        return result;
    }

    private static Path ensureScript() throws IOException {
        Path s = SCRIPT_PATH;
        if (s != null && Files.exists(s)) return s;
        synchronized (SCRIPT_LOCK) {
            s = SCRIPT_PATH;
            if (s == null || !Files.exists(s)) {
                Path target = Path.of(System.getProperty("java.io.tmpdir"), "yurii_universal_opt.py");
                Files.writeString(target, SCRIPT_BODY, StandardCharsets.UTF_8);
                target.toFile().deleteOnExit();
                SCRIPT_PATH = target;
                probeScipy();
                s = target;
            }
        }
        return s;
    }

    private static void probeScipy() {
        if (SCIPY_AVAILABLE != null) return;
        try {
            Process p = new ProcessBuilder(pythonExecutable(), "-c",
                    "import importlib,sys;sys.exit(0 if importlib.util.find_spec('scipy.optimize') else 1)")
                    .redirectErrorStream(true).start();
            boolean done = p.waitFor(5, TimeUnit.SECONDS);
            SCIPY_AVAILABLE = done && p.exitValue() == 0;
        } catch (Exception e) {
            SCIPY_AVAILABLE = false;
        }
    }

    private static String pythonExecutable() {
        return System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("win") ? "python" : "python3";
    }

    /** Inlined from {@code AnalyzerCore.readAll} so this class is self-contained. */
    private static String readAll(InputStream in) throws IOException {
        try (BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) {
                if (sb.length() > 0) sb.append('\n');
                sb.append(line);
            }
            return sb.toString();
        }
    }
}
