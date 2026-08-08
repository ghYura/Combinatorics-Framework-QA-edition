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

package com.company.utils.jmol;

import com.company.utils.jmol.ArrayUtil;
import com.company.utils.jmol.Logger;

import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Vector;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public class ZipUtil {

public static boolean isZipFile(InputStream is) throws Exception {
byte[] abMagic = new byte[4];
is.mark(5);
int countRead = is.read(abMagic, 0, 4);
is.reset();
return (countRead == 4 && abMagic[0] == (byte) 0x50 && abMagic[1] == (byte) 0x4B
&& abMagic[2] == (byte) 0x03 && abMagic[3] == (byte) 0x04);
}

public static boolean isZipFile(byte[] bytes) throws Exception {
return (bytes.length > 4
&& bytes[0] == 0x50
&& bytes[1] == 0x4B
&& bytes[2] == 0x03
&& bytes[3] == 0x04);
}


static public Object getZipFileContents(InputStream is, String[] list,
int listPtr, boolean asInputStream) {
StringBuffer ret = new StringBuffer();
if (list == null || listPtr >= list.length)
return getZipDirectoryAsStringAndClose(is);
String fileName = list[listPtr];
ZipInputStream zis = new ZipInputStream(is);
ZipEntry ze;
try {
boolean isAll = (fileName.equals("."));
if (isAll || fileName.lastIndexOf("/") == fileName.length() - 1) {
while ((ze = zis.getNextEntry()) != null) {
String name = ze.getName();
if (isAll || name.startsWith(fileName))
ret.append(name).append('\n');
}
if (asInputStream)
return new ByteArrayInputStream(ret.toString().getBytes(StandardCharsets.UTF_8));
return ret.toString();
}
while ((ze = zis.getNextEntry()) != null) {
if (!fileName.equals(ze.getName()))
continue;
byte[] bytes = getZipEntryAsBytes(zis);
if (isZipFile(bytes))
return getZipFileContents(new BufferedInputStream(
new ByteArrayInputStream(bytes)), list, ++listPtr, asInputStream);
if (asInputStream)
return new ByteArrayInputStream(bytes);
return new String(bytes);
}
} catch (Exception e) {
}
return "";
}

static public byte[] getZipFileContentsAsBytes(InputStream is, String[] list,
int listPtr) {
byte[] ret = new byte[0];
String fileName = list[listPtr];
if (fileName.lastIndexOf("/") == fileName.length() - 1)
return ret;
ZipInputStream zis = new ZipInputStream(is);
ZipEntry ze;
try {
while ((ze = zis.getNextEntry()) != null) {
if (!fileName.equals(ze.getName()))
continue;
byte[] bytes = getZipEntryAsBytes(zis);
if (isZipFile(bytes) && list != null && ++listPtr < list.length)
return getZipFileContentsAsBytes(new BufferedInputStream(
new ByteArrayInputStream(bytes)), list, listPtr);
return bytes;
}
} catch (Exception e) {
}
return ret;
}

static public String getZipDirectoryAsStringAndClose(InputStream is) {
StringBuffer sb = new StringBuffer();
String[] s = new String[0];
try {
s = getZipDirectoryOrErrorAndClose(is, false);
is.close();
} catch (Exception e) {
Logger.error(e.getMessage());
}
for (int i = 0; i < s.length; i++)
sb.append(s[i]).append('\n');
return sb.toString();
}

static public String[] getZipDirectoryAndClose(InputStream is, boolean addManifest) {
String[] s = new String[0];
try {
s = getZipDirectoryOrErrorAndClose(is, addManifest);
is.close();
} catch (Exception e) {
Logger.error(e.getMessage());
}
return s;
}

private static String[] getZipDirectoryOrErrorAndClose(InputStream is, boolean addManifest) throws IOException {
Vector<String> v = new Vector<>();
ZipInputStream zis = new ZipInputStream(is);
ZipEntry ze;
String manifest = null;
while ((ze = zis.getNextEntry()) != null) {
String fileName = ze.getName();
if (addManifest && fileName.equals("JmolManifest"))
manifest = getZipEntryAsString(zis);
else
v.addElement(fileName);
}
zis.close();
if (addManifest)
v.add(0, manifest == null ? "" : manifest + "\n############\n");
int len = v.size();
String[] dirList = new String[len];
for (int i = 0; i < len; i++)
dirList[i] = (String) v.elementAt(i);
return dirList;
}

public static String getZipEntryAsString(ZipInputStream zis) throws IOException {
StringBuffer sb = new StringBuffer();
byte[] buf = new byte[1024];
int len;
while (zis.available() == 1 && (len = zis.read(buf)) > 0)
sb.append(new String(buf, 0, len));
return sb.toString();
}

public static byte[] getZipEntryAsBytes(ZipInputStream zis) throws IOException {



byte[] buf = new byte[1024];
byte[] bytes = new byte[4096];
int len = 0;
int totalLen = 0;
while (zis.available() == 1 && (len = zis.read(buf)) > 0) {
totalLen += len;
if (totalLen >= bytes.length)
bytes = ArrayUtil.ensureLength(bytes, totalLen * 2);
System.arraycopy(buf, 0, bytes, totalLen - len, len);
}
buf = new byte[totalLen];
System.arraycopy(bytes, 0, buf, 0, totalLen);
return buf;
}

public static byte[] getStreamAsBytes(BufferedInputStream bis) throws IOException {
byte[] buf = new byte[1024];
byte[] bytes = new byte[4096];
int len = 0;
int totalLen = 0;
while ((len = bis.read(buf)) > 0) {
totalLen += len;
if (totalLen >= bytes.length)
bytes = ArrayUtil.ensureLength(bytes, totalLen * 2);
System.arraycopy(buf, 0, bytes, totalLen - len, len);
}
buf = new byte[totalLen];
System.arraycopy(bytes, 0, buf, 0, totalLen);
return buf;
}
}
