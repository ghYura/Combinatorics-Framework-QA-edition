package com.company;

import java.util.ArrayList;
import java.util.List;

public class StringButQuotesRefiner {

private List<String> oneSpace2AddBeforeCharsButNotInQuotesList = new ArrayList<>();
private List<String> oneSpace2AddAfterCharsButNotInQuotesList = new ArrayList<>();
private List<String> newLine2AddBeforeThatStartsWithButNotInQuotesList = new ArrayList<>();
private List<String> newLine2AddAfterThatEndsWithButNotInQuotesList = new ArrayList<>();
private String inputStr = "  1  \r  if   \n  (  b  =  1  -  2  |  |  2  %  0  )   \r\n   d  =  b  ; \"   w1  \\\\r\\\\n  1  *  \\\\r  =  i  \\\\n  +  +  ; \\\"   \\\\\"  txt  \\r\\n   +  \\r  +  \\n  i  ;   \"   w1  1  *  =  i  +  +  ;   +  +  i  ;    else  d  =  2  *  2  ;  { (( ( 2 * 2 )) ); } ab_c1   d_ef2  gh_3 jk  =  '  0xA  '  lm  =  '  a  '  (  ans  (  this  )  >  =  ans  (  {  1  ,  2  }  )  and (  cond  (  {  3  ,  4  }  )  or  ans  (  this  )  <  =  ans  (  {  5  ,  6  }  )  )  ,  7  ,  8  )  and  {  111  }  >  {  222  }  or  ans  (  this  )  =  \"  hello    my friend and  or  \"  and  (  cond  (  {  1  ,  2  }  )  $1  123   ; ";
private StringBuilder sb = new StringBuilder();

public void dummyTest(){
System.out.println("TEST:");
System.out.println("INPUT:\n"+ this.inputStr +"\n:INPUT");
String temp = removeNewLines(this.inputStr);
System.out.println("removeNewLines(this.inputStr) 1_technical_line_between:\n"+ temp +"\n:removeNewLines(this.inputStr)");
System.out.println("\nshrinkManySpacedStringExceptAnyQuoted(inputStr) 1_technical_line_between:\n"+ shrinkManySpacedStringExceptAnyQuoted(temp) +"\n:shrinkManySpacedStringExceptAnyQuoted(inputStr)");
System.out.println(":TEST");
}

public String removeCommentsFromMultipleLinedString(String strComments){

String noCommentStr;
boolean isdQuoteFoundAndReplacedWithDquoteAndSpace = false;
if (strComments.matches("\"")){
noCommentStr = strComments.replaceAll("\"", "\" ");
isdQuoteFoundAndReplacedWithDquoteAndSpace = true;
} else {
noCommentStr = strComments;
}
noCommentStr = noCommentStr.replaceAll( "//.*|(\"(?:\\\\[^\"]|\\\\\"|.)*?\")|(?s)/\\*.*?\\*/", "$1 " );
if (isdQuoteFoundAndReplacedWithDquoteAndSpace){
noCommentStr = noCommentStr.replaceAll("\"\\s", "\"");
}


return noCommentStr;
}

public String removeNewLines(String inputStr){
sb.setLength(0);
inputStr = inputStr.replaceAll("\\R(?<![\\\\])", " ");

sb.append(inputStr);
String strNL = sb.toString();
sb.setLength(0);
return strNL;
}

public String shrinkManySpacedStringExceptAnyQuoted(String inputStr){

sb.setLength(0);


String dsQuotes = "(?=([^\"]*\"[^\"]*\")*[^\"]*$)";
String sQuotes = "(?=([^']*'[^']*')*[^']*$)";




if (inputStr.matches(".*(\"){1,}.*((?<!\\\\){1}\"){1,}.*")){

String[] splits = inputStr.split("((?<!\\\\){1}\")");
for (int i = 0; i < splits.length; i++) {

if (i%2 == 0){
if (splits[i].matches(".*('){1,}.*('){1,}.*")){
String[] splits2 = splits[i].split("'");
for(int j = 0; j < splits2.length; j++){

if (j%2 == 0) {
sb.append(applyAffixRules(method(splits2[j])));
} else {
sb.append("'"+ splits2[j] +"'");
}
}
} else {
sb.append(applyAffixRules(method(splits[i])));
}

}
else {
sb.append("\""+ splits[i] +"\"");
}
}

} else {


if (inputStr.matches(".*('){1,}.*('){1,}.*")){
String[] splits3 = inputStr.split("'");

for(int k = 0; k < splits3.length; k++){

if (k%2 == 0){
sb.append(applyAffixRules(method(splits3[k])));
} else {
sb.append("'"+ splits3[k] +"'");
}
}
} else {
sb.append(applyAffixRules(method(inputStr)));
}
}
System.out.println("--------------------------------------------------------");


String str = sb.toString();



sb.setLength(0);
return str;
}

// ── dedup 2026-05-30: the 4 identical affix-rule blocks (were inlined per quote-split branch) ──
// Applies the optional add-before / add-after / newline-before / newline-after token rules in the
// SAME order as before. The old per-block `if(!list.isEmpty())` guards were redundant (a loop over
// an empty list is a no-op) — behaviour is byte-identical to the 4 inlined copies.
private String applyAffixRules(String cur) {
for (String tok : getOneSpace2AddBeforeCharsButNotInQuotesList())
cur = cur.replaceAll(tok, " " + tok);
for (String tok : getOneSpace2AddAfterCharsButNotInQuotesList())
cur = cur.replaceAll(tok, tok + " ");
for (String tok : getNewLine2AddBeforeThatStartsWithButNotInQuotesList())
cur = cur.replaceAll(tok, "\n" + tok);
for (String tok : getNewLine2AddAfterThatEndsWithButNotInQuotesList())
cur = cur.replaceAll(tok, tok + "\n");
return cur;
}

// ── [Bundle-bred refactor 2026-05-30 — unit P1 TextRefiner] ──────────────────────────────
// Adopted the winning quote/space-preserving "shrink" semantics, bred + verified through the
// Core→Reader→Executor loop (4/4 winners; the shipped variant FAILED its own golden). The
// ORIGINAL second .replaceAll(...) DELETED whitespace at word boundaries — the documented
// destructive behaviour that cfg().preserveWhitespace() was bolted on to bypass
// (e.g. " latency=10ms" → "latency=10ms";  'x  "y   z"  w' → 'x"y   z"w'). The winner keeps
// ONLY the run-collapse (≥2 whitespace → one space), leaving single spaces + quoted content
// intact (method() receives already quote-stripped segments from the caller).
// Original (for recovery — see .bak.beforeBundleAdopt):
//   return inp.replaceAll("(\\s|\\t){2,}(?=([^']*'[^']*')*[^']*$)", " ")
//             .replaceAll("((?<!')\\B(\\s|\\t){1,}((?<!')\\B))|(\\b(\\s|\\t){1,}((?<!')\\B))|((?<!')\\B(\\s|\\t){1,}\\b)", "");
private static String method(String inp){
return inp.replaceAll("(\\s|\\t){2,}(?=([^']*'[^']*')*[^']*$)", " ");
}

public List<String> getOneSpace2AddBeforeCharsButNotInQuotesList() {
return oneSpace2AddBeforeCharsButNotInQuotesList;
}

public void setOneSpace2AddBeforeCharsButNotInQuotesList(List<String> oneSpace2AddBeforeCharsButNotInQuotesList) {
this.oneSpace2AddBeforeCharsButNotInQuotesList = oneSpace2AddBeforeCharsButNotInQuotesList;
}

public List<String> getOneSpace2AddAfterCharsButNotInQuotesList() {
return oneSpace2AddAfterCharsButNotInQuotesList;
}

public void setOneSpace2AddAfterCharsButNotInQuotesList(List<String> oneSpace2AddAfterCharsButNotInQuotesList) {
this.oneSpace2AddAfterCharsButNotInQuotesList = oneSpace2AddAfterCharsButNotInQuotesList;
}

public List<String> getNewLine2AddBeforeThatStartsWithButNotInQuotesList() {
return newLine2AddBeforeThatStartsWithButNotInQuotesList;
}

public void setNewLine2AddBeforeThatStartsWithButNotInQuotesList(List<String> newLine2AddBeforeThatStartsWithButNotInQuotesList) {
this.newLine2AddBeforeThatStartsWithButNotInQuotesList = newLine2AddBeforeThatStartsWithButNotInQuotesList;
}

public List<String> getNewLine2AddAfterThatEndsWithButNotInQuotesList() {
return newLine2AddAfterThatEndsWithButNotInQuotesList;
}

public void setNewLine2AddAfterThatEndsWithButNotInQuotesList(List<String> newLine2AddAfterThatEndsWithButNotInQuotesList) {
this.newLine2AddAfterThatEndsWithButNotInQuotesList = newLine2AddAfterThatEndsWithButNotInQuotesList;
}
}
