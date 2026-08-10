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

package com.company.utils;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;


public class PowerShellCommand {

private static final Logger log = LogManager.getLogger(PowerShellCommand.class);

static String powerShellExe = "powershell.exe  ";

public static void command(String command) throws IOException {
String psh = powerShellExe + command;


log.info("PowerShell command: {}", psh);

Process powerShellProcess = Runtime.getRuntime().exec(psh);
powerShellProcess.getOutputStream().close();


log.debug("PowerShell standard output:");

String line;
var stdout = new BufferedReader(
new InputStreamReader(powerShellProcess.getInputStream()));
while ((line = stdout.readLine()) != null) {

log.info("[psql stdout] {}", line);
}
stdout.close();


log.debug("PowerShell standard error:");

var stderr = new BufferedReader(
new InputStreamReader(powerShellProcess.getErrorStream()));
while ((line = stderr.readLine()) != null) {

log.error("[psql stderr] {}", line);
}
stderr.close();


log.info("PowerShell command completed.");
}
}
