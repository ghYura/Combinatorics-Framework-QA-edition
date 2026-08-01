package com.company.helpers;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.util.regex.Matcher;
import java.util.regex.Pattern;


public class RegexUtils {

private static final Logger log = LogManager.getLogger(RegexUtils.class);

public static String getFirstRegexStringOf(String input, String rx) {
Pattern p = Pattern.compile(rx);
Matcher matcher = p.matcher(input);
if (matcher.find()) {

log.debug("Regex '{}' matched: '{}'", rx, matcher.group());
return matcher.group();
}
return null;
}
}
