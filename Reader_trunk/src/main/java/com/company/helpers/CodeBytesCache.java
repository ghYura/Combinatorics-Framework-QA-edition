package com.company.helpers;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;


public final class CodeBytesCache {
private CodeBytesCache() {}

public static Map<Short, byte[]> fromBAOSMap(Map<Short, java.io.ByteArrayOutputStream> src) {
final ConcurrentHashMap<Short, byte[]> dst = new ConcurrentHashMap<>(
Math.max(16, (int)(src.size() * 1.5))
);
for (Map.Entry<Short, java.io.ByteArrayOutputStream> e : src.entrySet()) {
java.io.ByteArrayOutputStream baos = e.getValue();
dst.put(e.getKey(), (baos != null) ? baos.toByteArray() : new byte[0]);
}
return dst;
}
}
