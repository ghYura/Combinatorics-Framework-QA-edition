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

package com.company.utils.jmol;

import java.io.PrintStream;


public class DefaultLogger implements LoggerInterface {


protected void log(PrintStream out, int level, String txt, Throwable e) {
if ((out != null) && ((txt != null) || (e != null))) {
txt = (txt != null ? txt : "");
out.println(
(Logger.logLevel() ? "[" + Logger.getLevel(level) + "] " : "") +
txt +
(e != null ? ": " + e.getMessage() : ""));
if (e != null) {
StackTraceElement[] elements = e.getStackTrace();
if (elements != null) {
for (int i = 0; i < elements.length; i++) {
out.println(
elements[i].getClassName() + " - " +
elements[i].getLineNumber() + " - " +
elements[i].getMethodName());
}
}
}
}
}


public void debug(String txt) {
log(System.out, Logger.LEVEL_DEBUG, txt, null);
}


public void info(String txt) {
log(System.out, Logger.LEVEL_INFO, txt, null);
}


public void warn(String txt) {
log(System.out, Logger.LEVEL_WARN, txt, null);
}


public void warn(String txt, Throwable e) {
log(System.out, Logger.LEVEL_WARN, txt, e);
}


public void error(String txt) {
log(System.err, Logger.LEVEL_ERROR, txt, null);
}


public void error(String txt, Throwable e) {
log(System.err, Logger.LEVEL_ERROR, txt, e);
}


public void fatal(String txt) {
log(System.err, Logger.LEVEL_FATAL, txt, null);
}


public void fatal(String txt, Throwable e) {
log(System.err, Logger.LEVEL_FATAL, txt, e);
}
}
