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

import org.codehaus.janino.SimpleCompiler;

/**
 * Native Janino fast path for source that fits Janino's supported Java subset.
 */
public final class JaninoCompilerBackend implements DynamicJavaCompiler {
    @Override
    public String name() {
        return "janino";
    }

    @Override
    public CompiledJavaClass compile(CompilationRequest request) throws Exception {
        SimpleCompiler compiler = new SimpleCompiler();
        compiler.setParentClassLoader(request.parentClassLoader());
        compiler.cook(request.sourceFileName(), request.source());

        ClassLoader loader = compiler.getClassLoader();
        Class<?> type = loader.loadClass(request.binaryClassName());
        // Keep the compiler reachable for the lifetime of its generated class loader.
        return new CompiledJavaClass(name(), type, loader, compiler, null);
    }
}
