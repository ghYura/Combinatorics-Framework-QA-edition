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
