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

import com.company.compiler.AdaptiveJavaCompiler;
import com.company.compiler.DynamicJavaCompiler;
import com.company.compiler.CompiledJavaClass;
import java.io.File;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.*;
import java.util.*;

/** Compiles each assembled candidate with the chosen backend (janino|ecj|adaptive),
 *  resolving deps from a -dirJars-style dir, runs main(), reads FW_VAR. Mirrors what
 *  MainWatch does, so it is a faithful pre-flight for combinability + backend capability. */
public class CompileProbe {
    public static void main(String[] args) throws Exception {
        AdaptiveJavaCompiler.Mode mode = AdaptiveJavaCompiler.Mode.fromProperty(args[0]);
        File depDir = new File(args[1]);
        List<URL> urls = new ArrayList<>();
        File[] jars = depDir.listFiles((d, n) -> n.endsWith(".jar"));
        if (jars != null) for (File j : jars) urls.add(j.toURI().toURL());
        URLClassLoader parent = new URLClassLoader(urls.toArray(new URL[0]), CompileProbe.class.getClassLoader());
        List<File> cp = new ArrayList<>(Arrays.asList(jars == null ? new File[0] : jars));
        AdaptiveJavaCompiler compiler = new AdaptiveJavaCompiler();
        int ok = 0, fail = 0;
        for (int i = 2; i < args.length; i++) {
            File f = new File(args[i]);
            String src = Files.readString(f.toPath());
            String cls = "C" + f.getName().replace(".java", "").replaceAll("[^A-Za-z0-9_]", "_");
            src = src.replaceFirst("\\b(class|interface|enum|record)\\s+\\w+", "$1 " + cls)
                     .replaceAll("\\bCandidate\\b", cls);
            try {
                DynamicJavaCompiler.CompilationRequest req =
                    DynamicJavaCompiler.CompilationRequest.forSource(cls, src, parent, cp, 21);
                try (CompiledJavaClass compiled = compiler.compile(req, mode)) {
                    Class<?> t = compiled.type();
                    Method m = t.getMethod("main", String[].class);
                    m.invoke(null, (Object) new String[0]);
                    int fw = t.getDeclaredField("FW_VAR").getInt(null);
                    System.out.println(f.getName() + " OK backend=" + compiled.backend() + " FW_VAR=" + fw);
                    ok++;
                }
            } catch (Throwable t) {
                Throwable c = t.getCause() != null ? t.getCause() : t;
                System.out.println(f.getName() + " FAILED " + c.getClass().getSimpleName() + ": " +
                    String.valueOf(c.getMessage()).replaceAll("\\s+", " ").substring(0, Math.min(160, String.valueOf(c.getMessage()).length())));
                fail++;
            }
        }
        System.out.println("PROBE mode=" + mode + " ok=" + ok + " fail=" + fail);
        if (fail > 0) System.exit(1);
    }
}
