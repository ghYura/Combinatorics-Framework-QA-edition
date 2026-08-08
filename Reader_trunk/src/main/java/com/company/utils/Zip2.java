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

import net.lingala.zip4j.io.outputstream.ZipOutputStream;
import net.lingala.zip4j.model.ZipModel;
import net.lingala.zip4j.model.ZipParameters;
import net.lingala.zip4j.model.enums.AesKeyStrength;
import net.lingala.zip4j.model.enums.CompressionLevel;
import net.lingala.zip4j.model.enums.CompressionMethod;
import net.lingala.zip4j.model.enums.EncryptionMethod;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class Zip2 {

public static byte[] method(String fileNameInZip, String str) {

ZipParameters zipParam = new ZipParameters();


zipParam.setCompressionMethod(CompressionMethod.DEFLATE);
zipParam.setCompressionLevel(CompressionLevel.NORMAL);
zipParam.setEncryptFiles(false);
zipParam.setEncryptionMethod(EncryptionMethod.NONE);
zipParam.setAesKeyStrength(AesKeyStrength.KEY_STRENGTH_256);


ByteArrayOutputStream bo = new ByteArrayOutputStream();
ZipOutputStream zout = null;
try {
zout = new ZipOutputStream(bo, StandardCharsets.UTF_8);


zipParam.setFileNameInZip(fileNameInZip);
zout.putNextEntry(zipParam);
zout.write(str.getBytes(StandardCharsets.UTF_8));
zout.closeEntry();

zout.flush();
zout.close();

return bo.toByteArray();
} catch (IOException e) {
e.printStackTrace();
}

return null;
}
}
