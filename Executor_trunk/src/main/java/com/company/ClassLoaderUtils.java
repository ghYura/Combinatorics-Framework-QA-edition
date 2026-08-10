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

package com.company;

import sun.misc.Unsafe;

import java.lang.reflect.Field;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.ArrayList;


public class ClassLoaderUtils {
// NOTE: intentional low-level access (Janino-style dynamic classpath surgery on
// jdk.internal.loader.ClassLoaders$* via sun.misc.Unsafe). Kept by design — do NOT
// rewrite to VarHandle (it cannot read the internal `ucp`/`path` fields the same way).
// "deprecation" suppresses Unsafe.objectFieldOffset; the residual "internal proprietary
// API" notes are not annotation-suppressible. At runtime on JDK 21+ launch with:
//   --add-opens java.base/jdk.internal.loader=ALL-UNNAMED
@SuppressWarnings({ "restriction", "unchecked", "deprecation" })
public static URL[] getUrls(ClassLoader classLoader) {
if (classLoader instanceof URLClassLoader) {
return ((URLClassLoader) classLoader).getURLs();
}


if (classLoader.getClass().getName().startsWith("jdk.internal.loader.ClassLoaders$")) {
try {
Field field = Unsafe.class.getDeclaredField("theUnsafe");
field.setAccessible(true);
Unsafe unsafe = (Unsafe) field.get(null);


Field ucpField = classLoader.getClass().getDeclaredField("ucp");
long ucpFieldOffset = unsafe.objectFieldOffset(ucpField);
Object ucpObject = unsafe.getObject(classLoader, ucpFieldOffset);


Field pathField = ucpField.getType().getDeclaredField("path");
long pathFieldOffset = unsafe.objectFieldOffset(pathField);
ArrayList<URL> path = (ArrayList<URL>) unsafe.getObject(ucpObject, pathFieldOffset);

return path.toArray(new URL[path.size()]);
} catch (Exception e) {
e.printStackTrace();
return null;
}
}
return null;
}
}
