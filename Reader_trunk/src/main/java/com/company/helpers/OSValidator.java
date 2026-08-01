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
