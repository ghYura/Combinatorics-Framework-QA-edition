package com.company.helpers;

public class CodeLineNumber {

public static int getLineNumber() {
return Thread.currentThread().getStackTrace()[2].getLineNumber();
}
}
