package com.company.file;

import com.company.helpers.OSValidator;

import java.io.*;

import static com.company.helpers.OSValidator.isMac;

public class FileReaderTODO {

public static long getLongLineCount(File file) throws IOException {

char ch = OSValidator.isMac() ? '\r' : '\n';

try (BufferedInputStream is = new BufferedInputStream(new FileInputStream(file), 1024)) {

byte[] c = new byte[1024];
boolean empty = true,
lastEmpty = false;
long count = 0;
int read;
while ((read = is.read(c)) != -1) {
for (int i = 0; i < read; i++) {
if (c[i] == ch) {
count++;
lastEmpty = true;
} else if (lastEmpty) {
lastEmpty = false;
}
}
empty = false;
}

if (!empty) {
if (count == 0) {
count = 1;
} else if (!lastEmpty) {
count++;
}
}

return count;
}
}
}
