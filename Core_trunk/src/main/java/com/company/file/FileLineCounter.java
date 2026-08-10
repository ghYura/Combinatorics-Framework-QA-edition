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

package com.company.file;

import com.company.helpers.OSValidator;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;


public class FileLineCounter {


public static long getLongLineCount(File file) throws IOException {
char ch = OSValidator.isMac() ? '\r' : '\n';

try (BufferedInputStream is = new BufferedInputStream(new FileInputStream(file), 1024)) {
byte[] c       = new byte[1024];
boolean empty  = true;
boolean lastEmpty = false;
long count = 0;
int  read;

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
if (count == 0)      count = 1;
else if (!lastEmpty) count++;
}

return count;
}
}
}
