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

package com.company;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.util.*;


public class StringButQuotesRefiner {

private static final Logger log = LogManager.getLogger(StringButQuotesRefiner.class);

private List<String> oneSpace2AddBeforeCharsButNotInQuotesList      = new ArrayList<>();
private List<String> oneSpace2AddAfterCharsButNotInQuotesList       = new ArrayList<>();
private List<String> newLine2AddBeforeThatStartsWithButNotInQuotesList = new ArrayList<>();
private List<String> newLine2AddAfterThatEndsWithButNotInQuotesList  = new ArrayList<>();



private final StringBuilder sb = new StringBuilder();



public void dummyTest() {
String input = "  1  \r  if   \n  (  b  =  1  -  2  |  |  2  %  0  )   \r\n   d  =  b  ; "
+ "\"   w1  \\\\r\\\\n  1  *  \\\\r  =  i  \\\\n  +  +  ; \\\"   \\\\\\\"  txt  "
+ "\\r\\n   +  \\r  +  \\n  i  ;   \"   w1  1  *  =  i  +  +  ;   +  +  i  ; "
+ "   else  d  =  2  *  2  ;  { (( ( 2 * 2 )) ); }";

log.info("TEST input: {}", input);
String temp = removeNewLines(input);
log.info("removeNewLines result: {}", temp);
log.info("shrink result: {}", shrinkManySpacedStringExceptAnyQuoted(temp));
}



public String removeNewLines(String inputStr) {
sb.setLength(0);
inputStr = inputStr.replaceAll("\\R(?<![\\\\])", " ");
sb.append(inputStr);
String strNL = sb.toString();
sb.setLength(0);
return strNL;
}


@Deprecated
public String removeComments(String strComment) {
sb.setLength(0);
if (strComment.matches("^.*////.*$|^.*///*.*/*//")) {
sb.append(strComment.replaceAll("//.*|(\"(?:\\\\[^\"]|\\\\\"|.)*?\")|(?s)/\\*.*?\\*/", "$1 "));
} else {
sb.append(strComment);
}
String noCommStr = sb.toString();
sb.setLength(0);
return noCommStr;
}

public String removeCommentsFromMultipleLinedString(String strComments) {
String noCommentStr;
boolean dQuoteReplaced = false;
if (strComments.matches("\"")) {
noCommentStr = strComments.replaceAll("\"", "\" ");
dQuoteReplaced = true;
} else {
noCommentStr = strComments;
}
noCommentStr = noCommentStr.replaceAll("//.*|(\"(?:\\\\[^\"]|\\\\\"|.)*?\")|(?s)/\\*.*?\\*/", "$1 ");
if (dQuoteReplaced) {
noCommentStr = noCommentStr.replaceAll("\"\\s", "\"");
}
return noCommentStr;
}


public String shrinkManySpacedStringExceptAnyQuoted(String inputStr) {
sb.setLength(0);



String[] dSplits = inputStr.split("((?<!\\\\){1}\")");

for (int i = 0; i < dSplits.length; i++) {
if (i % 2 == 0) {

String[] sSplits = dSplits[i].split("'");
for (int j = 0; j < sSplits.length; j++) {
if (j % 2 == 0) {

sb.append(processSegment(sSplits[j]));
} else {

sb.append("'").append(sSplits[j]).append("'");
}
}
} else {

sb.append("\"").append(dSplits[i]).append("\"");
}
}


log.trace("shrinkManySpacedStringExceptAnyQuoted result length: {}", sb.length());

String result = sb.toString();
sb.setLength(0);
return result;
}




private String processSegment(String seg) {


String result = seg.replaceAll("(\\s|\\t){2,}(?=([^']*'[^']*')*[^']*$)", " ")
.replaceAll("((?<!')\\B(\\s|\\t){1,}((?<!')\\B))|(\\b(\\s|\\t){1,}((?<!')\\B))|((?<!')\\B(\\s|\\t){1,}\\b)", "");


for (var pattern : oneSpace2AddBeforeCharsButNotInQuotesList) {
result = result.replaceAll(pattern, " " + pattern);
}

for (var pattern : oneSpace2AddAfterCharsButNotInQuotesList) {
result = result.replaceAll(pattern, pattern + " ");
}

for (var pattern : newLine2AddBeforeThatStartsWithButNotInQuotesList) {
result = result.replaceAll(pattern, "\n" + pattern);
}

for (var pattern : newLine2AddAfterThatEndsWithButNotInQuotesList) {
result = result.replaceAll(pattern, pattern + "\n");
}
return result;
}



public List<String> getOneSpace2AddBeforeCharsButNotInQuotesList() {
return oneSpace2AddBeforeCharsButNotInQuotesList;
}
public void setOneSpace2AddBeforeCharsButNotInQuotesList(List<String> l) {
this.oneSpace2AddBeforeCharsButNotInQuotesList = l;
}
public List<String> getOneSpace2AddAfterCharsButNotInQuotesList() {
return oneSpace2AddAfterCharsButNotInQuotesList;
}
public void setOneSpace2AddAfterCharsButNotInQuotesList(List<String> l) {
this.oneSpace2AddAfterCharsButNotInQuotesList = l;
}
public List<String> getNewLine2AddBeforeThatStartsWithButNotInQuotesList() {
return newLine2AddBeforeThatStartsWithButNotInQuotesList;
}
public void setNewLine2AddBeforeThatStartsWithButNotInQuotesList(List<String> l) {
this.newLine2AddBeforeThatStartsWithButNotInQuotesList = l;
}
public List<String> getNewLine2AddAfterThatEndsWithButNotInQuotesList() {
return newLine2AddAfterThatEndsWithButNotInQuotesList;
}
public void setNewLine2AddAfterThatEndsWithButNotInQuotesList(List<String> l) {
this.newLine2AddAfterThatEndsWithButNotInQuotesList = l;
}






public static final class SqlSourceCompactor {


public String compact(String sql) {
if (sql == null || sql.isBlank()) return sql;




String noLineComments = sql.replaceAll("--[^\\n]*", "");


String noBlockComments = noLineComments.replaceAll("(?s)/\\*.*?\\*/", " ");


String singleLine = noBlockComments.replaceAll("\\R", " ");



String[] parts = singleLine.split("'", -1);
var sb = new StringBuilder();
for (int i = 0; i < parts.length; i++) {
if (i % 2 == 0) {

sb.append(parts[i].replaceAll("\\s{2,}", " ").trim());
} else {

sb.append("'").append(parts[i]).append("'");
}
}
return sb.toString().trim();
}
}


public static final class JsonSourceCompactor {


public String compact(String json) {
if (json == null || json.isBlank()) return json;

var sb = new StringBuilder();
boolean inString = false;
boolean escaped  = false;

for (int i = 0; i < json.length(); i++) {
char c = json.charAt(i);
if (escaped) {
sb.append(c);
escaped = false;
continue;
}
if (c == '\\' && inString) {
sb.append(c);
escaped = true;
continue;
}
if (c == '"') {
inString = !inString;
sb.append(c);
continue;
}
if (!inString && Character.isWhitespace(c)) {
continue;
}
sb.append(c);
}
return sb.toString();
}
}


public static final class XmlSourceCompactor {


public String compact(String xml) {
if (xml == null || xml.isBlank()) return xml;


String noInterTagSpace = xml.replaceAll(">\\s+<", "><");




String[] tagSplits = noInterTagSpace.split("(?<=>)|(?=<)");
var sb = new StringBuilder();
for (var part : tagSplits) {
if (part.startsWith("<") && !part.startsWith("</") && !part.startsWith("<!")) {

sb.append(compactTagAttributes(part));
} else {

sb.append(part.strip());
}
}
return sb.toString();
}

private String compactTagAttributes(String tag) {

String[] parts = tag.split("(?<=[\"'])|(?=[\"'])");
var sb = new StringBuilder();
boolean inQuote = false;
char quoteChar = 0;
for (var p : parts) {
if (!inQuote && (p.equals("\"") || p.equals("'"))) {
inQuote = true; quoteChar = p.charAt(0);
sb.append(p);
} else if (inQuote && p.length() == 1 && p.charAt(0) == quoteChar) {
inQuote = false;
sb.append(p);
} else if (inQuote) {
sb.append(p);
} else {
sb.append(p.replaceAll("\\s{2,}", " "));
}
}
return sb.toString();
}
}
}
