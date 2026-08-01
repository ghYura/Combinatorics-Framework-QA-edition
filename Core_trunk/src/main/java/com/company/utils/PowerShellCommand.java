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
