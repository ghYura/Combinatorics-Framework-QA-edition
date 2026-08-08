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

package com.company;


public class PrintPretty {



private static volatile boolean isPrintPretty = false;


public static void configure(boolean enabled) {
isPrintPretty = enabled;
}



public enum Color {
RESET("\033[0m"),
BLACK("\033[0;30m"),   RED("\033[0;31m"),     GREEN("\033[0;32m"),
YELLOW("\033[0;33m"),  BLUE("\033[0;34m"),    MAGENTA("\033[0;35m"),
CYAN("\033[0;36m"),    WHITE("\033[0;37m"),
ORANGE("\033[48;2;255;165;0m"),
K("\033[0;30m"),  R("\033[0;31m"),  G("\033[0;32m"),  Y("\033[0;33m"),
B("\033[0;34m"),  M("\033[0;35m"),  C("\033[0;36m"),  W("\033[0;37m"),
BLACK_BOLD("\033[1;30m"),    RED_BOLD("\033[1;31m"),
GREEN_BOLD("\033[1;32m"),    YELLOW_BOLD("\033[1;33m"),
BLUE_BOLD("\033[1;34m"),     MAGENTA_BOLD("\033[1;35m"),
CYAN_BOLD("\033[1;36m"),     WHITE_BOLD("\033[1;37m"),
KB("\033[1;30m"),  RB("\033[1;31m"),  GB("\033[1;32m"),  YB("\033[1;33m"),
BB("\033[1;34m"),  MB("\033[1;35m"),  CB("\033[1;36m"),  WB("\033[1;37m"),
BLACK_UNDERLINED("\033[4;30m"),  RED_UNDERLINED("\033[4;31m"),
GREEN_UNDERLINED("\033[4;32m"),  YELLOW_UNDERLINED("\033[4;33m"),
BLUE_UNDERLINED("\033[4;34m"),   MAGENTA_UNDERLINED("\033[4;35m"),
CYAN_UNDERLINED("\033[4;36m"),   WHITE_UNDERLINED("\033[4;37m"),
KU("\033[4;30m"), RU("\033[4;31m"), GU("\033[4;32m"), YU("\033[4;33m"),
BU("\033[4;34m"), MU("\033[4;35m"), CU("\033[4;36m"), WU("\033[4;37m"),
BLACK_BACKGROUND("\033[40m"),  RED_BACKGROUND("\033[41m"),
GREEN_BACKGROUND("\033[42m"),  YELLOW_BACKGROUND("\033[43m"),
BLUE_BACKGROUND("\033[44m"),   MAGENTA_BACKGROUND("\033[45m"),
CYAN_BACKGROUND("\033[46m"),   WHITE_BACKGROUND("\033[47m"),
KBG("\033[40m"), RBG("\033[41m"), GBG("\033[42m"), YBG("\033[43m"),
BBG("\033[44m"), MBG("\033[45m"), CBG("\033[46m"), WBG("\033[47m"),
BLACK_BRIGHT("\033[0;90m"),   RED_BRIGHT("\033[0;91m"),
GREEN_BRIGHT("\033[0;92m"),   YELLOW_BRIGHT("\033[0;93m"),
BLUE_BRIGHT("\033[0;94m"),    MAGENTA_BRIGHT("\033[0;95m"),
CYAN_BRIGHT("\033[0;96m"),    WHITE_BRIGHT("\033[0;97m"),
KBR("\033[0;90m"), RBR("\033[0;91m"), GBR("\033[0;92m"), YBR("\033[0;93m"),
BBR("\033[0;94m"), MBR("\033[0;95m"), CBR("\033[0;96m"), WBR("\033[0;97m"),
BLACK_BOLD_BRIGHT("\033[1;90m"),   RED_BOLD_BRIGHT("\033[1;91m"),
GREEN_BOLD_BRIGHT("\033[1;92m"),   YELLOW_BOLD_BRIGHT("\033[1;93m"),
BLUE_BOLD_BRIGHT("\033[1;94m"),    MAGENTA_BOLD_BRIGHT("\033[1;95m"),
CYAN_BOLD_BRIGHT("\033[1;96m"),    WHITE_BOLD_BRIGHT("\033[1;97m"),
KBBR("\033[1;90m"), RBBR("\033[1;91m"), GBBR("\033[1;92m"), YBBR("\033[1;93m"),
BBBR("\033[1;94m"), MBBR("\033[1;95m"), CBBR("\033[1;96m"), WBBR("\033[1;97m"),
BLACK_BACKGROUND_BRIGHT("\033[0;100m"),  RED_BACKGROUND_BRIGHT("\033[0;101m"),
GREEN_BACKGROUND_BRIGHT("\033[0;102m"),  YELLOW_BACKGROUND_BRIGHT("\033[0;103m"),
BLUE_BACKGROUND_BRIGHT("\033[0;104m"),   MAGENTA_BACKGROUND_BRIGHT("\033[0;105m"),
CYAN_BACKGROUND_BRIGHT("\033[0;106m"),   WHITE_BACKGROUND_BRIGHT("\033[0;107m"),
KBGBR("\033[0;100m"), RBGBR("\033[0;101m"), GBGBR("\033[0;102m"),
YBGBR("\033[0;103m"), BBGBR("\033[0;104m"), MBGBR("\033[0;105m"),
CBGBR("\033[0;106m"), WBGBR("\033[0;107m");

private final String code;
Color(String code) { this.code = code; }

@Override
public String toString() { return code; }
}



public static void print(Color color, String str) {
if (isPrintPretty) System.out.print(color + str + Color.RESET);
else               System.out.print(str);
}

public static void println(Color color, String str) {
if (isPrintPretty) System.out.println(color + str + Color.RESET);
else               System.out.println(str);
}

public static void print(String str) {
if (isPrintPretty) System.out.print("\033[1m\u001B[31m" + str + "\u001B[0m\033[0m");
else               System.out.print(str);
}

public static void println(String str) {
if (isPrintPretty) System.out.println("\033[1m\u001B[31m" + str + "\u001B[0m\033[0m");
else               System.out.println(str);
}
}
