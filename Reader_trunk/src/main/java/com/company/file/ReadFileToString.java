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
