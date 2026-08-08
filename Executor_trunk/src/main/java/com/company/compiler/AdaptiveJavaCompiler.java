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

package com.company.compiler;

import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Janino fast path with an ECJ fallback for unsupported or modern Java source.
 */
public final class AdaptiveJavaCompiler {
    private static final Pattern MODERN_KEYWORD = Pattern.compile(
            "\\b(?:record|sealed|permits|yield)\\b|\\bnon-sealed\\b|\\bvar\\s+[A-Za-z_$]");

    private final DynamicJavaCompiler janino;
    private final DynamicJavaCompiler ecj;

    public AdaptiveJavaCompiler() {
        this(new JaninoCompilerBackend(), new EcjCompilerBackend());
    }

    AdaptiveJavaCompiler(DynamicJavaCompiler janino, DynamicJavaCompiler ecj) {
        this.janino = janino;
        this.ecj = ecj;
    }

    public CompiledJavaClass compile(DynamicJavaCompiler.CompilationRequest request, Mode mode)
            throws Exception {
        return switch (mode) {
            case JANINO -> janino.compile(request);
            case ECJ -> ecj.compile(request);
            case ADAPTIVE -> compileAdaptive(request);
        };
    }

    private CompiledJavaClass compileAdaptive(DynamicJavaCompiler.CompilationRequest request)
            throws Exception {
        if (likelyRequiresEcj(request.source())) {
            return ecj.compile(request);
        }
        try {
            return janino.compile(request);
        } catch (Exception janinoFailure) {
            try {
                return ecj.compile(request);
            } catch (Exception ecjFailure) {
                ecjFailure.addSuppressed(janinoFailure);
                throw ecjFailure;
            }
        }
    }

    static boolean likelyRequiresEcj(String source) {
        return source.contains("->")
                || source.contains("::")
                || MODERN_KEYWORD.matcher(source).find();
    }

    public enum Mode {
        ADAPTIVE,
        JANINO,
        ECJ;

        public static Mode fromProperty(String configuredValue) {
            String value = configuredValue == null
                    ? "adaptive"
                    : configuredValue.trim().toLowerCase(Locale.ROOT);
            return switch (value) {
                case "", "adaptive", "auto", "simple" -> ADAPTIVE;
                case "janino" -> JANINO;
                case "ecj" -> ECJ;
                default -> throw new IllegalArgumentException(
                        "Unsupported -Dfw.exec.compiler=" + configuredValue
                                + " (expected adaptive, janino, ecj, or javac)");
            };
        }
    }
}
