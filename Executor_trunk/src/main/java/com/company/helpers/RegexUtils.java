package com.company.helpers;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexUtils {

public static String getFirstRegexStringOf(String input, String rx){

Pattern p = Pattern.compile(rx);
Matcher matcher = p.matcher(input);
if (matcher.find()){
System.out.println(matcher.group());
return matcher.group();
} else return null;
}
}
