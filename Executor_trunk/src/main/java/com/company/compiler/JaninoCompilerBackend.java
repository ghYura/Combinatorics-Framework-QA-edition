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
