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
