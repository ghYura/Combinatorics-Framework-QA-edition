package com.company;

public class PrintPretty {

public static void print(String str){
System.out.print("\033[1m\u001B[31m" + str + "\u001B[0m\033[0m");
}

public static void println(String str){
System.out.println("\033[1m\u001B[31m" + str + "\u001B[0m\033[0m");
}
}
