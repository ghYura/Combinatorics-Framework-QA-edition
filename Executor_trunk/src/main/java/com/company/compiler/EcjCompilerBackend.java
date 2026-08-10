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

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;

import org.eclipse.jdt.internal.compiler.tool.EclipseCompiler;

/**
 * Full Java compiler fallback backed by ECJ. Source and generated classes stay in memory.
 */
public final class EcjCompilerBackend implements DynamicJavaCompiler {
    @Override
    public String name() {
        return "ecj";
    }

    @Override
    public CompiledJavaClass compile(CompilationRequest request) throws Exception {
        JavaCompiler compiler = new EclipseCompiler();
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        StandardJavaFileManager standardManager = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8);

        Map<String, byte[]> generatedClasses;
        Path sourceDirectory = Files.createTempDirectory("fw-ecj-source-");
        Path sourcePath = sourceDirectory.resolve(request.sourceFileName());
        try {
            Files.writeString(sourcePath, request.source(), StandardCharsets.UTF_8);
            try (MemoryJavaFileManager fileManager = new MemoryJavaFileManager(standardManager)) {
                List<String> options = compilerOptions(request);
                Iterable<? extends JavaFileObject> compilationUnits =
                        standardManager.getJavaFileObjects(sourcePath.toFile());
                Boolean success = compiler.getTask(
                        null, fileManager, diagnostics, options, null, compilationUnits).call();
                if (!Boolean.TRUE.equals(success)) {
                    throw new EcjCompilationException(request.binaryClassName(), formatDiagnostics(diagnostics));
                }
                generatedClasses = fileManager.generatedClasses();
            }
        } finally {
            deleteQuietly(sourcePath);
            deleteQuietly(sourceDirectory);
        }

        MemoryClassLoader loader = new MemoryClassLoader(request.parentClassLoader(), generatedClasses);
        try {
            Class<?> type = loader.loadClass(request.binaryClassName());
            return new CompiledJavaClass(name(), type, loader, compiler, loader);
        } catch (Exception | LinkageError failure) {
            loader.close();
            throw failure;
        }
    }

    private static List<String> compilerOptions(CompilationRequest request) {
        List<String> options = new ArrayList<>();
        options.add("-proc:none");
        options.add("-encoding");
        options.add(StandardCharsets.UTF_8.name());
        options.add("-source");
        options.add(Integer.toString(request.javaRelease()));
        options.add("-target");
        options.add(Integer.toString(request.javaRelease()));

        String classPath = buildClassPath(request.parentClassLoader(), request.classPath());
        if (!classPath.isBlank()) {
            options.add("-classpath");
            options.add(classPath);
        }
        return options;
    }

    private static String buildClassPath(ClassLoader parent, Collection<File> additionalEntries) {
        Set<String> entries = new LinkedHashSet<>();
        String processClassPath = System.getProperty("java.class.path", "");
        if (!processClassPath.isBlank()) {
            for (String entry : processClassPath.split(java.util.regex.Pattern.quote(File.pathSeparator))) {
                if (!entry.isBlank()) {
                    entries.add(new File(entry).getAbsolutePath());
                }
            }
        }

        for (ClassLoader loader = parent; loader != null; loader = loader.getParent()) {
            if (loader instanceof URLClassLoader urlLoader) {
                for (URL url : urlLoader.getURLs()) {
                    if ("file".equalsIgnoreCase(url.getProtocol())) {
                        try {
                            entries.add(new File(url.toURI()).getAbsolutePath());
                        } catch (Exception ignored) {
                            // Explicit additionalEntries still cover watched dependency JARs.
                        }
                    }
                }
            }
        }
        for (File entry : additionalEntries) {
            entries.add(entry.getAbsolutePath());
        }
        return String.join(File.pathSeparator, entries);
    }

    private static String formatDiagnostics(DiagnosticCollector<JavaFileObject> diagnostics) {
        if (diagnostics.getDiagnostics().isEmpty()) {
            return "ECJ reported compilation failure without diagnostics";
        }
        return diagnostics.getDiagnostics().stream()
                .map(EcjCompilerBackend::formatDiagnostic)
                .collect(Collectors.joining(System.lineSeparator()));
    }

    private static String formatDiagnostic(Diagnostic<? extends JavaFileObject> diagnostic) {
        String sourceName = diagnostic.getSource() == null
                ? "<source>"
                : diagnostic.getSource().getName();
        return sourceName + ":" + diagnostic.getLineNumber() + ":" + diagnostic.getColumnNumber()
                + ": " + diagnostic.getKind().name().toLowerCase(Locale.ROOT)
                + ": " + diagnostic.getMessage(Locale.ROOT);
    }

    private static void deleteQuietly(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (Exception ignored) {
            // Cleanup must not replace the compiler's diagnostic with a temp-file failure.
        }
    }

    public static final class EcjCompilationException extends Exception {
        EcjCompilationException(String binaryClassName, String diagnostics) {
            super("ECJ failed to compile " + binaryClassName + ":" + System.lineSeparator() + diagnostics);
        }
    }

    private static final class ByteCodeJavaFileObject extends SimpleJavaFileObject {
        private final ByteArrayOutputStream output = new ByteArrayOutputStream();

        ByteCodeJavaFileObject(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/') + kind.extension), kind);
        }

        @Override
        public ByteArrayOutputStream openOutputStream() {
            return output;
        }

        byte[] bytes() {
            return output.toByteArray();
        }
    }

    private static final class MemoryJavaFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ByteCodeJavaFileObject> generated = new LinkedHashMap<>();

        MemoryJavaFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) {
            ByteCodeJavaFileObject output = new ByteCodeJavaFileObject(className, kind);
            generated.put(className, output);
            return output;
        }

        Map<String, byte[]> generatedClasses() {
            Map<String, byte[]> result = new LinkedHashMap<>();
            generated.forEach((name, file) -> result.put(name, file.bytes()));
            return result;
        }
    }

    private static final class MemoryClassLoader extends ClassLoader implements AutoCloseable {
        private final Map<String, byte[]> generatedClasses;

        MemoryClassLoader(ClassLoader parent, Map<String, byte[]> generatedClasses) {
            super(parent);
            this.generatedClasses = new LinkedHashMap<>(generatedClasses);
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] byteCode = generatedClasses.get(name);
            if (byteCode == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, byteCode, 0, byteCode.length);
        }

        @Override
        public void close() {
            generatedClasses.clear();
        }
    }
}
