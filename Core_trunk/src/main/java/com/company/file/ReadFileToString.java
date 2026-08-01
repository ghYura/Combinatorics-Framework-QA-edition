package com.company.file;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.stream.Stream;


public class ReadFileToString {

private static final Logger log = LogManager.getLogger(ReadFileToString.class);


public static String stringFromFile(String filePath) {


var sb = new StringBuilder();

try (Stream<String> stream = Files.lines(Paths.get(filePath), StandardCharsets.UTF_8)) {
stream.forEach(s -> sb.append(s).append("\n"));
} catch (IOException e) {
log.error("Failed to read file '{}': {}", filePath, e.getMessage(), e);
}

String str = sb.toString();

log.trace("Read file '{}': {} chars", filePath, str.length());
return str;
}
}
