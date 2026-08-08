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

package com.company.file;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.stream.Stream;

public class ReadFileToString {

private static StringBuffer sb = new StringBuffer();

public static synchronized String stringFromFile(String filePath) {

sb.setLength(0);

String str = readLineByLineJava8(filePath);
sb.setLength(0);
System.out.println(str);
return str;
}


private static synchronized String readLineByLineJava8(String filePath) {



try (Stream<String> stream = Files.lines(Paths.get(filePath), StandardCharsets.UTF_8)){
stream.forEach(s -> sb.append(s).append("\n"));
} catch (IOException e){
e.printStackTrace();
}

return sb.toString();
}
}
