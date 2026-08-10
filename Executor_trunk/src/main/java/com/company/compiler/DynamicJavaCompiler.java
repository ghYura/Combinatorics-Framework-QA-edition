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

package com.company.compiler;

import java.io.File;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Compiles one incoming Java source unit into an isolated class loader.
 */
public interface DynamicJavaCompiler {
    Pattern PACKAGE_DECLARATION = Pattern.compile(
            "(?m)^\\s*package\\s+([A-Za-z_$][\\w$]*(?:\\.[A-Za-z_$][\\w$]*)*)\\s*;");

    String name();

    CompiledJavaClass compile(CompilationRequest request) throws Exception;

    record CompilationRequest(
            String sourceFileName,
            String binaryClassName,
            String source,
            ClassLoader parentClassLoader,
            List<File> classPath,
            int javaRelease) {

        public CompilationRequest {
            Objects.requireNonNull(sourceFileName, "sourceFileName");
            Objects.requireNonNull(binaryClassName, "binaryClassName");
            Objects.requireNonNull(source, "source");
            Objects.requireNonNull(parentClassLoader, "parentClassLoader");
            classPath = List.copyOf(Objects.requireNonNull(classPath, "classPath"));
            if (javaRelease < 8) {
                throw new IllegalArgumentException("javaRelease must be >= 8");
            }
        }

        public static CompilationRequest forSource(
                String simpleClassName,
                String source,
                ClassLoader parentClassLoader,
                Collection<File> classPath,
                int javaRelease) {
            Objects.requireNonNull(simpleClassName, "simpleClassName");
            Matcher packageMatcher = PACKAGE_DECLARATION.matcher(source);
            String binaryName = packageMatcher.find()
                    ? packageMatcher.group(1) + "." + simpleClassName
                    : simpleClassName;
            return new CompilationRequest(
                    simpleClassName + ".java",
                    binaryName,
                    source,
                    parentClassLoader,
                    List.copyOf(classPath),
                    javaRelease);
        }
    }
}
