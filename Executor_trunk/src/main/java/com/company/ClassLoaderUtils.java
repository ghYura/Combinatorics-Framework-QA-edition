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
