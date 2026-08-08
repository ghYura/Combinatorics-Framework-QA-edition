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

import static com.company.ReaderConfig.*;

public class PrintPretty {

public static void print(String str){
if (cfg().isPrintPretty()) System.out.print("\033[1m\u001B[31m" + str + "\u001B[0m\033[0m");
else System.out.print(str);
}

public static void println(String str){
if (cfg().isPrintPretty()) System.out.println("\033[1m\u001B[31m" + str + "\u001B[0m\033[0m");
else System.out.println(str);
}
}
