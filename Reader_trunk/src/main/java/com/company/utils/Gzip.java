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

package com.company.utils;

import org.apache.commons.io.IOUtils;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.zip.*;

public class Gzip {

public static byte[] str2deflate(String inpStr) {





byte[] input = inpStr.getBytes(StandardCharsets.UTF_8);
Deflater compresser = new Deflater();
try {
compresser.setInput(input);
compresser.finish();
ByteArrayOutputStream bos = new ByteArrayOutputStream(Math.max(64, input.length / 4));
byte[] buf = new byte[64 * 1024];
while (!compresser.finished()) {
int n = compresser.deflate(buf);
if (n > 0) bos.write(buf, 0, n);
}
return bos.toByteArray();
} finally {
compresser.end();
}
}

public static String byteArr2inflate(byte[] inpArr) {



Inflater decompresser = new Inflater();
try {
decompresser.setInput(inpArr, 0, inpArr.length);
ByteArrayOutputStream bos = new ByteArrayOutputStream(Math.max(64, inpArr.length * 4));
byte[] buf = new byte[64 * 1024];
try {
while (!decompresser.finished() && !decompresser.needsInput() && !decompresser.needsDictionary()) {
int n = decompresser.inflate(buf);
if (n == 0) break;
bos.write(buf, 0, n);
}
} catch (DataFormatException e) {
e.printStackTrace();
}
return bos.toString(StandardCharsets.UTF_8);
} finally {
decompresser.end();
}
}

public static byte[] compressIntoByteArr(String simpleString) {
try {
ByteArrayOutputStream bos = new ByteArrayOutputStream(simpleString.length());
GZIPOutputStream gzip = null;
gzip = new GZIPOutputStream(bos);
gzip.write(simpleString.getBytes());
gzip.close();
byte[] compressed = bos.toByteArray();
bos.close();
return compressed;
} catch (IOException e) {
e.printStackTrace();
}
return null;
}








public static String compressIntoBase64Str(String data) throws IOException {
ByteArrayOutputStream bos = new ByteArrayOutputStream(data.length());
GZIPOutputStream gzip = new GZIPOutputStream(bos);
gzip.write(data.getBytes(java.nio.charset.StandardCharsets.UTF_8));
gzip.close();
byte[] compressed = bos.toByteArray();
final String content = Base64.getEncoder().encodeToString(compressed);
bos.close();
return content;
}




public static String decompressByteArr(final byte[] compressed) throws IOException {
ByteArrayInputStream bis = new ByteArrayInputStream(compressed);
GZIPInputStream gis = new GZIPInputStream(bis);
byte[] bytes = IOUtils.toByteArray(gis);



return new String(bytes, StandardCharsets.UTF_8);
}

public static GZIPInputStream byteArr2GZIPInputStream(final byte[] compressed) {
ByteArrayInputStream bis = new ByteArrayInputStream(compressed);
GZIPInputStream gis = null;
try {
gis = new GZIPInputStream(bis);
} catch (IOException e) {
e.printStackTrace();
}





return gis;
}








public static String decompressBase64Str(final String compressedBase64Str) throws IOException {
final byte[] bytes0 = Base64.getDecoder().decode(compressedBase64Str);
ByteArrayInputStream bis = new ByteArrayInputStream(bytes0);
GZIPInputStream gis = new GZIPInputStream(bis);
byte[] bytes = IOUtils.toByteArray(gis);



return new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
}

public static void test(String[] args) {

String str1 = "Hello World ";
String str2 = "Java";

byte[] bytes = joinByteArray(str1.getBytes(), str2.getBytes());
byte[] bytes2 = joinByteArray2(str1.getBytes(), str2.getBytes());


System.out.println("Result       : " + new String(bytes));
System.out.println("Result (Hex) : " + convertBytesToHex(bytes));

System.out.println("Result2      : " + new String(bytes2));
System.out.println("Result2 (Hex): " + convertBytesToHex(bytes2));
}

public static byte[] joinByteArray(byte[] byte1, byte[] byte2) {

return ByteBuffer.allocate(byte1.length + byte2.length)
.put(byte1)
.put(byte2)
.array();
}

public static byte[] joinByteArray2(byte[] byte1, byte[] byte2) {

byte[] result = new byte[byte1.length + byte2.length];

System.arraycopy(byte1, 0, result, 0, byte1.length);
System.arraycopy(byte2, 0, result, byte1.length, byte2.length);

return result;
}

public static String convertBytesToHex(byte[] bytes) {
StringBuilder result = new StringBuilder();
for (byte temp : bytes) {
result.append(String.format("%02x", temp));
}
return result.toString();
}
}
