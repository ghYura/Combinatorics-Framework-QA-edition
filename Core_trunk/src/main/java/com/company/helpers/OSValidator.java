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

package com.company.helpers;

import com.company.PrintPretty;

public class OSValidator {

private static String OS = System.getProperty("os.name").toLowerCase();

public static String whatOS() {

PrintPretty.println(OS);

if (isWindows()) {
PrintPretty.println("This is Windows");
return "win";
} else if (isMac()) {
PrintPretty.println("This is Mac");
return "mac";
} else if (isUnix()) {
PrintPretty.println("This is Unix or Linux");
return "nix";
} else if (isSolaris()) {
PrintPretty.println("This is Solaris");
return "sunos";
} else {
PrintPretty.println("Your OS is not supported by OSValidator!!");
return "unknown";
}
}

public static boolean isWindows() {
return (OS.indexOf("win") >= 0);
}

public static boolean isMac() {
return (OS.indexOf("mac") >= 0);
}

public static boolean isUnix() {
return (OS.indexOf("nix") >= 0 || OS.indexOf("nux") >= 0 || OS.indexOf("aix") > 0);
}

public static boolean isSolaris() {
return (OS.indexOf("sunos") >= 0);
}
}
