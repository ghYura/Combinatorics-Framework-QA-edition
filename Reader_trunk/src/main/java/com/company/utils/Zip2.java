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
