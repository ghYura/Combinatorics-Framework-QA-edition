package com.company.helpers;

import com.company.PrintPretty;

import java.util.Collections;
import java.util.Scanner;
import java.util.concurrent.*;

public class InputWithTimeout {


static volatile boolean isAccepted = false;
static volatile String defMessage0 = "";
static volatile boolean run = true;
static volatile long start;
static String pattern0 = "([^yn]|(yes){0}|(no){0})(("+Choice.Y+")|("+Choice.YES+")|("+Choice.NO+")|("+Choice.N+"))+([^yn]|(yes){0}|(no){0})";
private static volatile int thisTout;
static volatile int i = 0;

public static void clearConsole() {

if (System.getProperty("os.name").contains("Windows")) {


}
else {

}

}

static void promptPrinter(String defMessage){

clearConsole();
defMessage = defMessage.replaceAll("\\d++", String.valueOf(thisTout-i));
PrintPretty.println(defMessage);

System.out.print("|");System.out.print(String.join("", Collections.nCopies(i++ +1, ".")));System.out.print(String.join("", Collections.nCopies(thisTout-i, " ")));System.out.print("| "+(thisTout+1-i));
System.out.println();




}






public static String getChoiceWithTimeout(Choice choiceDefault, String defMessage, String wrongChoiceMessage, int tout) {
thisTout = tout;
defMessage0 = defMessage;

isAccepted = false;
run = true;
i = 0;
Callable<String> k = () -> {Scanner scanner = new Scanner(System.in); return (scanner.hasNext()) ? scanner.nextLine() : "";};
start = System.currentTimeMillis();
String choice = "";
boolean valid;
ExecutorService l = Executors.newFixedThreadPool(1);
Future<String> g;
System.out.println("Enter your choice in "+tout+" seconds :");
g = l.submit(k);
System.out.print(String.join("", Collections.nCopies(thisTout, " ")));
PrintPretty.println(defMessage);

Thread thrToutChecker = new Thread(() -> {
while (run) {
try {
promptPrinter(defMessage0);
Thread.sleep(1000);
if (System.currentTimeMillis() - start > thisTout * 1000L) { run = false; }
if (isAccepted) break;
} catch (InterruptedException e) {
Thread.currentThread().interrupt();
return;
}
}
}, "input-timeout-checker");
thrToutChecker.setDaemon(true);
thrToutChecker.start();
done:
while (run) {

do {
valid = true;
if (g.isDone()) {
try {
choice = g.get().toLowerCase();
if (choice.equals(Choice.YES) ||
choice.equals(Choice.Y) ||
choice.equals(Choice.N) ||
choice.equals(Choice.NO) ||
choice.matches(pattern0)) {
valid = true;
isAccepted = true;
break done;
} else {
valid = false;
isAccepted = false;
throw new IllegalArgumentException();
}
} catch (InterruptedException | ExecutionException | IllegalArgumentException e) {


g = l.submit(k);
valid = false;
isAccepted = false;
}
}
} while (!valid);







}

g.cancel(true);

run = false;
l.shutdownNow();
String pattern = "("+Choice.Y+")|("+Choice.YES+")|("+Choice.NO+")|("+Choice.N+")";


 return ((choice.matches("") || !choice.matches(pattern)) ? choiceDefault.toString() : choice);
}

public enum Choice {
Y("y"),
YES("yes"),
NO("no"),
N("n");

private final String code;

Choice(String code) {
this.code = code;
}

@Override
public String toString() {
return code;
}
}
}
