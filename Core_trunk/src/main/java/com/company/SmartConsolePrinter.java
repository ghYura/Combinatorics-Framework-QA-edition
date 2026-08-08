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
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.company;

import java.io.InputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Pattern;


public final class SmartConsolePrinter {







private static volatile long CFG_flushIntervalMs = 2000L;


private static volatile int CFG_numberOfRowsFlushTrigger = 0;


private static volatile int CFG_collapseStrength = 50;


private static volatile int CFG_heuristicFuzzyLogic = 50;


private static volatile int CFG_maxQueueSize = 100_000;




private static boolean ENABLE_COLLAPSING = true;

private static boolean ENABLE_FUZZY = true;

private static boolean ENABLE_SMART_TEMPLATE = false;

private static boolean ENABLE_GRANULAR_TEMPLATE = false;

private static boolean ENABLE_CONSTANT_COMPACTION = false;

private static boolean ENABLE_CHAR_FOLDING = false;


private static int CHAR_FOLD_VISIBLE_CHARS = 80;

private static int CONSTANT_COMPACTION_MAX_LEN = 100;

private static double FUZZY_THRESHOLD = 0.50;

private static int MAX_OVERWRITE_WIDTH = 220;

private static int MIN_COLLAPSE_DISPLAY = 2;

private static int MAX_TEMPLATE_VARIANTS_DISPLAY = 5;



private static boolean ENABLE_TIMESTAMP_NORM = false;

private static boolean ENABLE_TEMPLATE_LIBRARY = false;

private static boolean ENABLE_LEVENSHTEIN = false;

private static boolean ENABLE_NGRAM = false;

private static boolean ENABLE_SEQUENCE_DETECTION = false;

private static boolean ENABLE_BLOCK_DETECTION = false;

private static boolean ENABLE_ANALYSIS_WORKER = false;

private static boolean ENABLE_ENTROPY = false;

private static boolean ENABLE_PREDICTIVE = false;


private static int HISTORY_CAPACITY = 0;

private static int TEMPLATE_LIBRARY_MAX = 0;

private static double LEVENSHTEIN_THRESHOLD = 0.70;

private static double NGRAM_THRESHOLD = 0.40;

private static int NGRAM_N = 3;

private static int MAX_CYCLE_PERIOD = 6;

private static int MAX_BLOCK_SIZE = 3;

private static int BLOCK_KNOWN_THRESHOLD = 2;





private static final Pattern P_ANSI       = Pattern.compile("\\033\\[[0-9;]*m");
private static final Pattern P_DIGITS     = Pattern.compile("\\d+");
private static final Pattern P_SQUOTED    = Pattern.compile("'[^']*'");
private static final Pattern P_DQUOTED    = Pattern.compile("\"[^\"]*\"");
private static final Pattern P_PATH_ABS   = Pattern.compile("(?<=[\\s(=:])(/[^\\s,;)]+)");
private static final Pattern P_PATH_WIN   = Pattern.compile("(?<=[\\s(=:])[A-Z]:\\\\[^\\s,;)]+");

private static final Pattern P_OBJ_HASH   = Pattern.compile("@[0-9a-fA-F]{4,32}\\b");

private static final Pattern P_ID_MIXED   = Pattern.compile("\\b[a-zA-Z_]*\\d+[a-zA-Z0-9_]*\\b");

private static final Pattern P_KV_VALUE   = Pattern.compile("(?<==)[^\\s,;)\\]]+");

private static final Pattern P_HEX        = Pattern.compile("\\b0x[0-9a-fA-F]+\\b|\\b[0-9a-fA-F]{6,}\\b");

private static final Pattern P_MULTISPACE = Pattern.compile("\\s{2,}");

private static final Pattern P_TOKEN_SPLIT = Pattern.compile("[^a-zA-Z0-9]+");

private static final Pattern P_VARLIKE_TOKEN = Pattern.compile(".*\\d.*|^.$|^[A-Z]{1,2}$");


private static final Pattern P_WORD_SPLIT = Pattern.compile("\\s+");

private static final Pattern P_GRANULAR_TOKENIZER = Pattern.compile("[a-zA-Z0-9]+|[^a-zA-Z0-9]");


private static final Pattern P_NEVER_COLLAPSE = Pattern.compile(
"(?i)" +
"\\[STALL|\\[TIMEOUT|\\[ORPHAN|\\[DEAD-THREAD|\\[WARN|\\[ERROR|\\[INFO\\]" +
"|Exception |^\\s+at |Caused by:|^\\s+\\.\\.\\. \\d+ more" +
"|===== |-----" +
"|java\\.[a-z]" +
"|REVIEW LINE CODE"
);


private static final Pattern P_TIMESTAMP_ISO = Pattern.compile(
"\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}([.,]\\d{1,6})?([+-]\\d{2}:?\\d{2}|Z)?");


private static final Pattern P_TIMESTAMP_TIME = Pattern.compile(
"\\b\\d{2}:\\d{2}:\\d{2}([.,]\\d{1,3})?\\b");


private static final Pattern P_EPOCH_MS = Pattern.compile("\\b1[0-9]{12}\\b");





private static final class Entry {
final String text;
final boolean isErr;
final boolean hasNewline;

Entry(String text, boolean isErr, boolean hasNewline) {
this.text = text;
this.isErr = isErr;
this.hasNewline = hasNewline;
}
}


static final class TemplateState {
String[] words;
Map<Integer, LinkedHashSet<String>> variantSets;
boolean valid;
boolean isGranular;

String originSkeleton;

TemplateState() {
this.variantSets = new HashMap<>();
this.valid = true;
}

void init(String line, boolean granular) {
this.isGranular = granular;
this.words = granular ? tokenizeGranular(line) : P_WORD_SPLIT.split(line);
this.valid = true;
this.variantSets.clear();
for (int i = 0; i < words.length; i++) {
LinkedHashSet<String> s = new LinkedHashSet<>();
s.add(words[i]);
variantSets.put(i, s);
}
}

private String[] tokenizeGranular(String s) {
List<String> list = new ArrayList<>();
java.util.regex.Matcher m = P_GRANULAR_TOKENIZER.matcher(s);
while (m.find()) list.add(m.group());
return list.toArray(new String[0]);
}

boolean merge(String line) {
if (!valid) return false;
String[] incoming = isGranular ? tokenizeGranular(line) : P_WORD_SPLIT.split(line);
if (incoming.length != words.length) {
valid = false;
return false;
}
for (int i = 0; i < words.length; i++) {
if (!words[i].equals(incoming[i])) {
LinkedHashSet<String> set = variantSets.get(i);
if (set == null) {
set = new LinkedHashSet<>();
set.add(words[i]);
variantSets.put(i, set);
}
if (set.size() < MAX_TEMPLATE_VARIANTS_COLLECT) {
set.add(incoming[i]);
}
}
}
return true;
}

String toDisplayString() {
if (!valid || words == null) return null;
StringBuilder result = new StringBuilder();
StringBuilder constantBuffer = new StringBuilder();

for (int i = 0; i < words.length; i++) {
LinkedHashSet<String> set = variantSets.get(i);
boolean isConstant = (set == null || set.size() <= 1);

if (isConstant) {
if (!isGranular && i > 0 && constantBuffer.length() > 0) {
constantBuffer.append(' ');
} else if (!isGranular && i > 0 && result.length() > 0 && result.charAt(result.length()-1) != ' ') {
constantBuffer.append(' ');
}
constantBuffer.append(words[i]);
} else {
flushConstantBuffer(result, constantBuffer);

if (!isGranular && i > 0 && result.length() > 0 && result.charAt(result.length()-1) != ' ') {
result.append(' ');
}

int size = set.size();
boolean isHexHash = true;
for (String v : set) {

if (!v.matches("[0-9a-fA-F]+") || v.length() < 3) {
isHexHash = false;
break;
}
}


if (size >= 4 && isHexHash && isGranular) {
result.append("{#}");
} else if (size >= MAX_TEMPLATE_VARIANTS_DISPLAY) {
result.append("{...}");
} else {
result.append('{');
int shown = 0;
for (String v : set) {
if (shown > 0) result.append('|');
result.append(v);
shown++;
}
result.append('}');
}
}
}
flushConstantBuffer(result, constantBuffer);
return result.toString();
}

private String applyVowellessCompaction(String text) {
StringBuilder sb = new StringBuilder(text.length());
boolean firstAlpha = true;
for (int i = 0; i < text.length(); i++) {
char c = text.charAt(i);
if (Character.isLetter(c)) {
if (firstAlpha) {
sb.append(c);
firstAlpha = false;
} else {
char lower = Character.toLowerCase(c);
if (lower != 'a' && lower != 'e' && lower != 'i' && lower != 'o' && lower != 'u' && lower != 'y') {
sb.append(c);
}
}
} else {
sb.append(c);
firstAlpha = true;
}
}
return sb.toString();
}

private void flushConstantBuffer(StringBuilder result, StringBuilder buffer) {
if (buffer.length() == 0) return;
String text = buffer.toString();
if (ENABLE_CONSTANT_COMPACTION && text.length() > CONSTANT_COMPACTION_MAX_LEN) {

text = applyVowellessCompaction(text);


if (text.length() > CONSTANT_COMPACTION_MAX_LEN) {
int keep = Math.max(1, CONSTANT_COMPACTION_MAX_LEN / 2);
text = text.substring(0, keep) + ".." + text.substring(text.length() - keep);
}
} else {
result.append(text);
buffer.setLength(0);
return;
}
result.append(text);
buffer.setLength(0);
}


TemplateState copy() {
TemplateState c = new TemplateState();
c.words = (words != null) ? Arrays.copyOf(words, words.length) : null;
c.valid = valid;
c.isGranular = isGranular;
c.originSkeleton = originSkeleton;
for (Map.Entry<Integer, LinkedHashSet<String>> e : variantSets.entrySet()) {
c.variantSets.put(e.getKey(), new LinkedHashSet<>(e.getValue()));
}
return c;
}
}


private static final int MAX_TEMPLATE_VARIANTS_COLLECT = 100;




private static String[] historySkeletons;

private static String[] historyRawLines;
private static int historyHead = 0;
private static int historyCount = 0;

private static void historyRecord(String skeleton, String rawLine) {
if (HISTORY_CAPACITY <= 0) return;
if (historySkeletons == null) {
historySkeletons = new String[HISTORY_CAPACITY];
historyRawLines = new String[HISTORY_CAPACITY];
}
historySkeletons[historyHead] = skeleton;
historyRawLines[historyHead] = rawLine;
historyHead = (historyHead + 1) % HISTORY_CAPACITY;
if (historyCount < HISTORY_CAPACITY) historyCount++;
}


private static String historyGetSkeleton(int offset) {
if (offset >= historyCount) return null;
int idx = (historyHead - 1 - offset + HISTORY_CAPACITY) % HISTORY_CAPACITY;
return historySkeletons[idx];
}




private static LinkedHashMap<String, TemplateState> templateLibrary;

private static void initTemplateLibrary() {
if (TEMPLATE_LIBRARY_MAX <= 0) return;
final int cap = TEMPLATE_LIBRARY_MAX;
templateLibrary = new LinkedHashMap<String, TemplateState>(cap + 1, 0.75f, true) {
@Override
protected boolean removeEldestEntry(Map.Entry<String, TemplateState> eldest) {
return size() > cap;
}
};
}


private static void librarySave(TemplateState tmpl) {
if (templateLibrary == null || tmpl == null || !tmpl.valid) return;
if (tmpl.originSkeleton == null) return;
templateLibrary.put(tmpl.originSkeleton, tmpl.copy());
}


private static TemplateState libraryMatch(String skeleton) {
if (templateLibrary == null || skeleton == null) return null;

TemplateState exact = templateLibrary.get(skeleton);
if (exact != null) return exact;

if (ENABLE_LEVENSHTEIN) {
for (Map.Entry<String, TemplateState> e : templateLibrary.entrySet()) {
if (levenshteinSimilarity(skeleton, e.getKey()) >= LEVENSHTEIN_THRESHOLD) {
return e.getValue();
}
}
}
return null;
}



private static LinkedHashMap<String, Integer> blockSignatureCounts;

private static void initBlockSignatures() {
final int cap = 256;
blockSignatureCounts = new LinkedHashMap<String, Integer>(cap + 1, 0.75f, true) {
@Override
protected boolean removeEldestEntry(Map.Entry<String, Integer> eldest) {
return size() > cap;
}
};
}


private static String buildBlockSignature(int blockSize) {
if (historyCount < blockSize) return null;
StringBuilder sb = new StringBuilder();
for (int i = blockSize - 1; i >= 0; i--) {
if (sb.length() > 0) sb.append('\u001F');
sb.append(historyGetSkeleton(i));
}
return sb.toString();
}


private static void recordBlockSignatures() {
if (blockSignatureCounts == null) return;
for (int bs = 2; bs <= MAX_BLOCK_SIZE && bs <= historyCount; bs++) {
String sig = buildBlockSignature(bs);
if (sig != null) {
blockSignatureCounts.merge(sig, 1, Integer::sum);
}
}
}


private static boolean isKnownBlockContinuation(String skeleton) {
if (blockSignatureCounts == null) return false;
for (int bs = 2; bs <= MAX_BLOCK_SIZE && bs <= historyCount; bs++) {

StringBuilder sb = new StringBuilder();
for (int i = bs - 2; i >= 0; i--) {
if (sb.length() > 0) sb.append('\u001F');
sb.append(historyGetSkeleton(i));
}
if (sb.length() > 0) sb.append('\u001F');
sb.append(skeleton);
String sig = sb.toString();
Integer count = blockSignatureCounts.get(sig);
if (count != null && count >= BLOCK_KNOWN_THRESHOLD) {
return true;
}
}
return false;
}




private static int detectedCyclePeriod = 0;

private static int cycleRepeatCount = 0;


private static boolean detectCycleMatch(String skeleton) {
if (HISTORY_CAPACITY <= 0 || historyCount < 2) return false;

if (detectedCyclePeriod > 0) {
String expected = historyGetSkeleton(detectedCyclePeriod - 1);
if (skeleton.equals(expected)) {
return true;
} else {
detectedCyclePeriod = 0;
cycleRepeatCount = 0;
}
}

for (int period = 2; period <= MAX_CYCLE_PERIOD && period * 2 <= historyCount; period++) {
boolean match = true;
for (int i = 0; i < period; i++) {
String a = historyGetSkeleton(i);
String b = historyGetSkeleton(i + period);
if (a == null || b == null || !a.equals(b)) {
match = false;
break;
}
}
if (match) {

String expected = historyGetSkeleton(period - 1);
if (skeleton.equals(expected)) {
detectedCyclePeriod = period;
cycleRepeatCount++;
return true;
}
}
}
return false;
}




private static final class AnalysisEngine implements Runnable {
final ConcurrentLinkedQueue<String> inbox = new ConcurrentLinkedQueue<>();

private final Map<String, int[]> frequencies = new HashMap<>();
private long totalSeen = 0;

volatile Map<String, Double> publishedEntropy = Collections.emptyMap();
volatile Set<String> publishedFrequentSkeletons = Collections.emptySet();

void postSkeleton(String skeleton) {

if (inbox.size() < 50_000) {
inbox.offer(skeleton);
}
}

@Override
public void run() {
while (!shutdownRequested) {
try { Thread.sleep(300); } catch (InterruptedException e) { break; }
String sk;
while ((sk = inbox.poll()) != null) {
int[] cnt = frequencies.get(sk);
if (cnt == null) {
cnt = new int[]{0};
frequencies.put(sk, cnt);
}
cnt[0]++;
totalSeen++;
}

if (frequencies.size() > 10_000) {
Iterator<Map.Entry<String, int[]>> it = frequencies.entrySet().iterator();
while (it.hasNext() && frequencies.size() > 5_000) {
Map.Entry<String, int[]> e = it.next();
if (e.getValue()[0] <= 1) it.remove();
}
}

if (totalSeen > 0) {
Map<String, Double> ent = new HashMap<>();
Set<String> freq = new HashSet<>();
double invLog2 = 1.0 / Math.log(2);
double freqThreshold = totalSeen * 0.02;
for (Map.Entry<String, int[]> e : frequencies.entrySet()) {
double p = (double) e.getValue()[0] / totalSeen;
ent.put(e.getKey(), -Math.log(p) * invLog2);
if (e.getValue()[0] >= freqThreshold) freq.add(e.getKey());
}
publishedEntropy = ent;
publishedFrequentSkeletons = freq;
}
}
}
}


private static volatile AnalysisEngine analysisEngine = null;




private static Map<String, int[]> inlineFrequencies;
private static long inlineTotalSeen = 0;

private static void inlineFreqRecord(String skeleton) {
if (inlineFrequencies == null) return;
int[] cnt = inlineFrequencies.get(skeleton);
if (cnt == null) {
cnt = new int[]{0};
inlineFrequencies.put(skeleton, cnt);
}
cnt[0]++;
inlineTotalSeen++;

if (inlineFrequencies.size() > 5_000) {
Iterator<Map.Entry<String, int[]>> it = inlineFrequencies.entrySet().iterator();
while (it.hasNext() && inlineFrequencies.size() > 2_500) {
Map.Entry<String, int[]> e = it.next();
if (e.getValue()[0] <= 1) it.remove();
}
}
}


private static double getEntropy(String skeleton) {
if (ENABLE_ANALYSIS_WORKER && analysisEngine != null) {
Double e = analysisEngine.publishedEntropy.get(skeleton);
return (e != null) ? e : -1.0;
}
if (inlineFrequencies != null && inlineTotalSeen > 10) {
int[] cnt = inlineFrequencies.get(skeleton);
if (cnt != null) {
double p = (double) cnt[0] / inlineTotalSeen;
return -Math.log(p) / Math.log(2);
}
}
return -1.0;
}


private static boolean isFrequentSkeleton(String skeleton) {
if (ENABLE_ANALYSIS_WORKER && analysisEngine != null) {
return analysisEngine.publishedFrequentSkeletons.contains(skeleton);
}
if (inlineFrequencies != null && inlineTotalSeen > 20) {
int[] cnt = inlineFrequencies.get(skeleton);
return cnt != null && cnt[0] >= inlineTotalSeen * 0.02;
}
return false;
}





private static final ConcurrentLinkedQueue<Entry> QUEUE = new ConcurrentLinkedQueue<>();

private static final AtomicInteger queueSize = new AtomicInteger(0);

private static final PrintStream REAL_OUT = System.out;
private static final PrintStream REAL_ERR = System.err;


private static String currentGroupSkeleton = null;
private static Set<String> currentGroupStructuralTokens = null;
private static String currentGroupLastText = null;
private static boolean currentGroupIsErr = false;
private static final AtomicInteger currentGroupCount = new AtomicInteger(0);

private static TemplateState currentGroupTemplate = null;





private static String prevGroupSkeleton = null;
private static Set<String> prevGroupStructuralTokens = null;
private static String prevGroupLastText = null;
private static boolean prevGroupIsErr = false;
private static int prevGroupCount = 0;
private static TemplateState prevGroupTemplate = null;

private static final Object FLUSH_LOCK = new Object();
private static final AtomicBoolean STARTED = new AtomicBoolean(false);
private static volatile boolean shutdownRequested = false;
private static final AtomicLong lastOverwriteLen = new AtomicLong(0);
private static volatile boolean configLoaded = false;

private static volatile Thread daemonThread = null;






public static void out(String s) {
ensureStarted();
enqueueOrFallback(s == null ? "null" : s, false, false);
}


public static void outln(String s) {
ensureStarted();
enqueueOrFallback(s == null ? "null" : s, false, true);
}


public static void outln() { outln(""); }


public static void err(String s) {
ensureStarted();
enqueueOrFallback(s == null ? "null" : s, true, false);
}


public static void errln(String s) {
ensureStarted();
enqueueOrFallback(s == null ? "null" : s, true, true);
}


public static void errln() { errln(""); }


public static void stackTrace(Throwable t) {
if (t == null) return;
StringWriter sw = new StringWriter();
t.printStackTrace(new PrintWriter(sw));
drainAndFlush();
enqueueOrFallback(sw.toString(), true, true);
drainAndFlush();
}


public static void shutdown() {
shutdownRequested = true;
drainAndFlush();
}



public static void out(Object o)   { out(String.valueOf(o)); }
public static void outln(Object o)  { outln(String.valueOf(o)); }
public static void err(Object o)   { err(String.valueOf(o)); }
public static void errln(Object o)  { errln(String.valueOf(o)); }

public static void out(int i)      { out(String.valueOf(i)); }
public static void outln(int i)     { outln(String.valueOf(i)); }
public static void err(int i)      { err(String.valueOf(i)); }
public static void errln(int i)     { errln(String.valueOf(i)); }

public static void out(long l)     { out(String.valueOf(l)); }
public static void outln(long l)    { outln(String.valueOf(l)); }
public static void err(long l)     { err(String.valueOf(l)); }
public static void errln(long l)    { errln(String.valueOf(l)); }

public static void out(boolean b)  { out(String.valueOf(b)); }
public static void outln(boolean b) { outln(String.valueOf(b)); }
public static void err(boolean b)  { err(String.valueOf(b)); }
public static void errln(boolean b) { errln(String.valueOf(b)); }

public static void out(char c)     { out(String.valueOf(c)); }
public static void outln(char c)    { outln(String.valueOf(c)); }
public static void out(double d)   { out(String.valueOf(d)); }
public static void outln(double d)  { outln(String.valueOf(d)); }






private static void enqueueOrFallback(String text, boolean isErr, boolean hasNewline) {
if (queueSize.get() >= CFG_maxQueueSize) {
PrintStream target = isErr ? REAL_ERR : REAL_OUT;
synchronized (FLUSH_LOCK) {
if (hasNewline) {
target.println(text);
} else {
target.print(text);
}
target.flush();
}
return;
}
QUEUE.offer(new Entry(text, isErr, hasNewline));
int newSize = queueSize.incrementAndGet();
if (CFG_numberOfRowsFlushTrigger > 0 && newSize >= CFG_numberOfRowsFlushTrigger) {
triggerRowCountFlush();
}
}

private static void triggerRowCountFlush() {
Thread t = daemonThread;
if (t != null) {
t.interrupt();
}
}

private static void ensureStarted() {
if (STARTED.compareAndSet(false, true)) {
loadConfig();

Thread daemon = new Thread(SmartConsolePrinter::flushLoop, "SmartConsolePrinter-daemon");
daemon.setDaemon(true);
daemon.setPriority(Thread.MIN_PRIORITY + 1);
daemonThread = daemon;
daemon.start();

Runtime.getRuntime().addShutdownHook(
new Thread(SmartConsolePrinter::shutdown, "SmartConsolePrinter-shutdown"));


Thread.setDefaultUncaughtExceptionHandler((thread, throwable) -> {
drainAndFlush();
StringWriter sw = new StringWriter();
sw.write("Exception in thread \"" + thread.getName() + "\" ");
throwable.printStackTrace(new PrintWriter(sw));
synchronized (FLUSH_LOCK) {
finaliseGroup();
REAL_ERR.println(sw.toString());
REAL_ERR.flush();
}
});


if (ENABLE_ANALYSIS_WORKER) {
analysisEngine = new AnalysisEngine();
Thread worker = new Thread(analysisEngine, "SmartConsolePrinter-analysis");
worker.setDaemon(true);
worker.setPriority(Thread.MIN_PRIORITY);
worker.start();
}
}
}





private static void loadConfig() {
if (configLoaded) return;
configLoaded = true;

Properties prop = new Properties();
try (InputStream in = Files.newInputStream(Paths.get("./fw.properties"))) {
prop.load(in);
} catch (Exception ignored) {
applyDerivedConfig();
return;
}

String valTimeDelta = prop.getProperty("SmartConsolePrinter.timeDeltaOfLogDataCollection");
if (valTimeDelta != null) {
try {
long seconds = Long.parseLong(valTimeDelta.trim());
if (seconds > 0) CFG_flushIntervalMs = seconds * 1000L;
} catch (NumberFormatException ignored) { }
}

String valRows = prop.getProperty("SmartConsolePrinter.numberOfRowsOfLogDataCollection");
if (valRows != null) {
try {
int rows = Integer.parseInt(valRows.trim());
if (rows >= 0) CFG_numberOfRowsFlushTrigger = rows;
} catch (NumberFormatException ignored) { }
}

String valCollapse = prop.getProperty("SmartConsolePrinter.collapseAndFoldingOfLogDataStrenght");
if (valCollapse != null) {
try {
int v = Integer.parseInt(valCollapse.trim());
CFG_collapseStrength = Math.max(0, Math.min(100, v));
} catch (NumberFormatException ignored) { }
}

String valHeuristic = prop.getProperty("SmartConsolePrinter.heuristicSmartFuzzyLogicOfLogDataAnalysis");
if (valHeuristic != null) {
try {
int v = Integer.parseInt(valHeuristic.trim());
CFG_heuristicFuzzyLogic = Math.max(0, Math.min(1000, v));
} catch (NumberFormatException ignored) { }
}

String valMaxQueue = prop.getProperty("SmartConsolePrinter.maxQueueSize");
if (valMaxQueue != null) {
try {
int v = Integer.parseInt(valMaxQueue.trim());
if (v > 0) CFG_maxQueueSize = v;
} catch (NumberFormatException ignored) { }
}

applyDerivedConfig();
}





private static void applyDerivedConfig() {
int Y = CFG_collapseStrength;
int Z = CFG_heuristicFuzzyLogic;


if (Y == 0) {
ENABLE_COLLAPSING    = false;
ENABLE_FUZZY         = false;
ENABLE_CHAR_FOLDING  = false;
MAX_OVERWRITE_WIDTH  = 9999;
FUZZY_THRESHOLD      = 1.0;
MIN_COLLAPSE_DISPLAY = 2;
} else if (Y <= 30) {
ENABLE_COLLAPSING    = true;
ENABLE_FUZZY         = false;
ENABLE_CHAR_FOLDING  = false;
MAX_OVERWRITE_WIDTH  = 300;
FUZZY_THRESHOLD      = 1.0;
MIN_COLLAPSE_DISPLAY = 2;
} else if (Y <= 60) {
ENABLE_COLLAPSING    = true;
ENABLE_FUZZY         = true;
ENABLE_CHAR_FOLDING  = false;
FUZZY_THRESHOLD      = 0.65 - (Y - 31) * (0.25 / 29.0);
MAX_OVERWRITE_WIDTH  = 220;
MIN_COLLAPSE_DISPLAY = 2;
} else if (Y <= 90) {
ENABLE_COLLAPSING    = true;
ENABLE_FUZZY         = true;
ENABLE_CHAR_FOLDING  = false;
FUZZY_THRESHOLD      = 0.35 - (Y - 61) * (0.25 / 29.0);
MAX_OVERWRITE_WIDTH  = 180 - (int) ((Y - 61) * (80.0 / 29.0));
MIN_COLLAPSE_DISPLAY = 2;
} else {
ENABLE_COLLAPSING    = true;
ENABLE_FUZZY         = true;
ENABLE_CHAR_FOLDING  = true;
FUZZY_THRESHOLD      = 0.05;
MAX_OVERWRITE_WIDTH  = 100 - (int) ((Y - 91) * (60.0 / 9.0));
if (MAX_OVERWRITE_WIDTH < 30) MAX_OVERWRITE_WIDTH = 30;
CHAR_FOLD_VISIBLE_CHARS = 60 - (int) ((Y - 91) * (40.0 / 9.0));
if (CHAR_FOLD_VISIBLE_CHARS < 15) CHAR_FOLD_VISIBLE_CHARS = 15;
MIN_COLLAPSE_DISPLAY = 1;
}




ENABLE_SMART_TEMPLATE   = false;
ENABLE_GRANULAR_TEMPLATE= false;
ENABLE_CONSTANT_COMPACTION = false;
CONSTANT_COMPACTION_MAX_LEN = 100;
ENABLE_TIMESTAMP_NORM   = false;
ENABLE_TEMPLATE_LIBRARY = false;
ENABLE_LEVENSHTEIN      = false;
ENABLE_NGRAM            = false;
ENABLE_SEQUENCE_DETECTION = false;
ENABLE_BLOCK_DETECTION  = false;
ENABLE_ANALYSIS_WORKER  = false;
ENABLE_ENTROPY          = false;
ENABLE_PREDICTIVE       = false;
HISTORY_CAPACITY        = 0;
TEMPLATE_LIBRARY_MAX    = 0;
MAX_TEMPLATE_VARIANTS_DISPLAY = 0;



if (Z > 0) {
ENABLE_COLLAPSING = true;
ENABLE_FUZZY      = true;
}

if (Z == 0) {
ENABLE_FUZZY = false;
} else if (Z <= 40) {

FUZZY_THRESHOLD = Math.min(FUZZY_THRESHOLD + 0.10, 0.90);
} else if (Z <= 100) {

ENABLE_SMART_TEMPLATE = true;
MAX_TEMPLATE_VARIANTS_DISPLAY = 3 + (int) ((Z - 41) * (4.0 / 59.0));
} else if (Z <= 200) {

ENABLE_SMART_TEMPLATE = true;
ENABLE_TIMESTAMP_NORM = true;
MAX_TEMPLATE_VARIANTS_DISPLAY = 7 + (int) ((Z - 101) * (5.0 / 99.0));
HISTORY_CAPACITY = 50;
} else if (Z <= 300) {

ENABLE_SMART_TEMPLATE = true;
ENABLE_TIMESTAMP_NORM = true;
ENABLE_TEMPLATE_LIBRARY = true;
ENABLE_GRANULAR_TEMPLATE = true;
ENABLE_CONSTANT_COMPACTION = true;
CONSTANT_COMPACTION_MAX_LEN = 50;
MAX_TEMPLATE_VARIANTS_DISPLAY = 12 + (int) ((Z - 201) * (3.0 / 99.0));
HISTORY_CAPACITY = 200;
TEMPLATE_LIBRARY_MAX = 64;
if (ENABLE_FUZZY) FUZZY_THRESHOLD = Math.max(FUZZY_THRESHOLD - 0.05, 0.05);
} else if (Z <= 400) {

ENABLE_SMART_TEMPLATE = true;
ENABLE_TIMESTAMP_NORM = true;
ENABLE_TEMPLATE_LIBRARY = true;
ENABLE_GRANULAR_TEMPLATE = true;
ENABLE_CONSTANT_COMPACTION = true;
CONSTANT_COMPACTION_MAX_LEN = 40;
ENABLE_LEVENSHTEIN = true;
MAX_TEMPLATE_VARIANTS_DISPLAY = 15;
HISTORY_CAPACITY = 300;
TEMPLATE_LIBRARY_MAX = 96;
LEVENSHTEIN_THRESHOLD = 0.70 - (Z - 301) * (0.20 / 99.0);
if (ENABLE_FUZZY) FUZZY_THRESHOLD = Math.max(FUZZY_THRESHOLD - 0.08, 0.05);
} else if (Z <= 500) {

ENABLE_SMART_TEMPLATE = true;
ENABLE_TIMESTAMP_NORM = true;
ENABLE_TEMPLATE_LIBRARY = true;
ENABLE_GRANULAR_TEMPLATE = true;
ENABLE_CONSTANT_COMPACTION = true;
CONSTANT_COMPACTION_MAX_LEN = 30;
ENABLE_LEVENSHTEIN = true;
ENABLE_NGRAM = true;
MAX_TEMPLATE_VARIANTS_DISPLAY = 18;
HISTORY_CAPACITY = 500;
TEMPLATE_LIBRARY_MAX = 128;
LEVENSHTEIN_THRESHOLD = 0.50;
NGRAM_THRESHOLD = 0.40 - (Z - 401) * (0.15 / 99.0);
if (ENABLE_FUZZY) FUZZY_THRESHOLD = Math.max(FUZZY_THRESHOLD - 0.12, 0.05);
} else if (Z <= 600) {

ENABLE_SMART_TEMPLATE = true;
ENABLE_TIMESTAMP_NORM = true;
ENABLE_TEMPLATE_LIBRARY = true;
ENABLE_GRANULAR_TEMPLATE = true;
ENABLE_CONSTANT_COMPACTION = true;
CONSTANT_COMPACTION_MAX_LEN = 25;
ENABLE_LEVENSHTEIN = true;
ENABLE_NGRAM = true;
ENABLE_SEQUENCE_DETECTION = true;
MAX_TEMPLATE_VARIANTS_DISPLAY = 20;
HISTORY_CAPACITY = 800;
TEMPLATE_LIBRARY_MAX = 160;
LEVENSHTEIN_THRESHOLD = 0.45;
NGRAM_THRESHOLD = 0.25;
MAX_CYCLE_PERIOD = 4 + (int) ((Z - 501) * (4.0 / 99.0));
if (ENABLE_FUZZY) FUZZY_THRESHOLD = Math.max(FUZZY_THRESHOLD - 0.15, 0.04);
} else if (Z <= 700) {

ENABLE_SMART_TEMPLATE = true;
ENABLE_TIMESTAMP_NORM = true;
ENABLE_TEMPLATE_LIBRARY = true;
ENABLE_GRANULAR_TEMPLATE = true;
ENABLE_CONSTANT_COMPACTION = true;
CONSTANT_COMPACTION_MAX_LEN = 20;
ENABLE_LEVENSHTEIN = true;
ENABLE_NGRAM = true;
ENABLE_SEQUENCE_DETECTION = true;
ENABLE_BLOCK_DETECTION = true;
MAX_TEMPLATE_VARIANTS_DISPLAY = 25;
HISTORY_CAPACITY = 1000;
TEMPLATE_LIBRARY_MAX = 200;
LEVENSHTEIN_THRESHOLD = 0.40;
NGRAM_THRESHOLD = 0.22;
MAX_CYCLE_PERIOD = 8;
MAX_BLOCK_SIZE = 3 + (int) ((Z - 601) * (2.0 / 99.0));
BLOCK_KNOWN_THRESHOLD = 2;
if (ENABLE_FUZZY) FUZZY_THRESHOLD = Math.max(FUZZY_THRESHOLD - 0.18, 0.03);
} else if (Z <= 800) {

ENABLE_SMART_TEMPLATE = true;
ENABLE_TIMESTAMP_NORM = true;
ENABLE_TEMPLATE_LIBRARY = true;
ENABLE_GRANULAR_TEMPLATE = true;
ENABLE_CONSTANT_COMPACTION = true;
CONSTANT_COMPACTION_MAX_LEN = 15;
ENABLE_LEVENSHTEIN = true;
ENABLE_NGRAM = true;
ENABLE_SEQUENCE_DETECTION = true;
ENABLE_BLOCK_DETECTION = true;
ENABLE_ANALYSIS_WORKER = true;
MAX_TEMPLATE_VARIANTS_DISPLAY = 30;
HISTORY_CAPACITY = 2000;
TEMPLATE_LIBRARY_MAX = 256;
LEVENSHTEIN_THRESHOLD = 0.35;
NGRAM_THRESHOLD = 0.20;
MAX_CYCLE_PERIOD = 10;
MAX_BLOCK_SIZE = 5;
BLOCK_KNOWN_THRESHOLD = 2;
if (ENABLE_FUZZY) FUZZY_THRESHOLD = Math.max(FUZZY_THRESHOLD - 0.20, 0.03);
} else if (Z <= 900) {

ENABLE_SMART_TEMPLATE = true;
ENABLE_TIMESTAMP_NORM = true;
ENABLE_TEMPLATE_LIBRARY = true;
ENABLE_GRANULAR_TEMPLATE = true;
ENABLE_CONSTANT_COMPACTION = true;
CONSTANT_COMPACTION_MAX_LEN = 10;
ENABLE_LEVENSHTEIN = true;
ENABLE_NGRAM = true;
ENABLE_SEQUENCE_DETECTION = true;
ENABLE_BLOCK_DETECTION = true;
ENABLE_ANALYSIS_WORKER = true;
ENABLE_ENTROPY = true;
MAX_TEMPLATE_VARIANTS_DISPLAY = 35;
HISTORY_CAPACITY = 3000;
TEMPLATE_LIBRARY_MAX = 384;
LEVENSHTEIN_THRESHOLD = 0.30;
NGRAM_THRESHOLD = 0.18;
MAX_CYCLE_PERIOD = 10;
MAX_BLOCK_SIZE = 5;
BLOCK_KNOWN_THRESHOLD = 2;
if (ENABLE_FUZZY) FUZZY_THRESHOLD = Math.max(FUZZY_THRESHOLD - 0.22, 0.03);
} else {

ENABLE_SMART_TEMPLATE = true;
ENABLE_TIMESTAMP_NORM = true;
ENABLE_TEMPLATE_LIBRARY = true;
ENABLE_GRANULAR_TEMPLATE = true;
ENABLE_CONSTANT_COMPACTION = true;
CONSTANT_COMPACTION_MAX_LEN = 5;
ENABLE_LEVENSHTEIN = true;
ENABLE_NGRAM = true;
ENABLE_SEQUENCE_DETECTION = true;
ENABLE_BLOCK_DETECTION = true;
ENABLE_ANALYSIS_WORKER = true;
ENABLE_ENTROPY = true;
ENABLE_PREDICTIVE = true;
MAX_TEMPLATE_VARIANTS_DISPLAY = 40 + (int) ((Z - 901) * (10.0 / 99.0));
HISTORY_CAPACITY = 5000;
TEMPLATE_LIBRARY_MAX = 512;
LEVENSHTEIN_THRESHOLD = 0.25;
NGRAM_THRESHOLD = 0.15;
MAX_CYCLE_PERIOD = 12;
MAX_BLOCK_SIZE = 6;
BLOCK_KNOWN_THRESHOLD = 1;
if (ENABLE_FUZZY) FUZZY_THRESHOLD = Math.max(FUZZY_THRESHOLD - 0.25, 0.02);
}


if (ENABLE_TEMPLATE_LIBRARY) initTemplateLibrary();
if (ENABLE_BLOCK_DETECTION) initBlockSignatures();



if (ENABLE_ENTROPY) {
inlineFrequencies = new LinkedHashMap<String, int[]>(2048, 0.75f, true) {
@Override
protected boolean removeEldestEntry(Map.Entry<String, int[]> eldest) {
return size() > 5000;
}
};
}
}




private static void flushLoop() {
while (!shutdownRequested) {
try {
Thread.sleep(CFG_flushIntervalMs);
} catch (InterruptedException e) {
Thread.interrupted();
}
drainAndFlush();
}
}

private static void drainAndFlush() {
synchronized (FLUSH_LOCK) {
Entry entry;
while ((entry = QUEUE.poll()) != null) {
queueSize.decrementAndGet();
processEntry(entry);
}
if (shutdownRequested) finaliseGroup();
}
}





private static void processEntry(Entry entry) {

if (!ENABLE_COLLAPSING) {
finaliseGroup();
PrintStream target = entry.isErr ? REAL_ERR : REAL_OUT;
if (entry.hasNewline) {
target.println(entry.text);
} else {
target.print(entry.text);
}
target.flush();
return;
}


if (!entry.hasNewline) {
finaliseGroup();
(entry.isErr ? REAL_ERR : REAL_OUT).print(entry.text);
(entry.isErr ? REAL_ERR : REAL_OUT).flush();
return;
}


if (isNeverCollapse(entry.text)) {
finaliseGroup();
PrintStream t = entry.isErr ? REAL_ERR : REAL_OUT;
t.println(entry.text);
t.flush();
lastOverwriteLen.set(0);
return;
}


String skeleton = ENABLE_TIMESTAMP_NORM ? toSkeletonTimestampAware(entry.text) : toSkeleton(entry.text);
Set<String> tokens = ENABLE_FUZZY ? structuralTokens(entry.text) : Collections.emptySet();


if (ENABLE_ANALYSIS_WORKER && analysisEngine != null) {
analysisEngine.postSkeleton(skeleton);
}


if (ENABLE_ENTROPY) {
inlineFreqRecord(skeleton);
}


if (currentGroupSkeleton != null && currentGroupIsErr == entry.isErr) {
if (isMatch(skeleton, tokens)) {

currentGroupCount.incrementAndGet();
currentGroupLastText = entry.text;
if (ENABLE_SMART_TEMPLATE && currentGroupTemplate != null) {
currentGroupTemplate.merge(entry.text);
}
historyRecord(skeleton, entry.text);
if (ENABLE_BLOCK_DETECTION) recordBlockSignatures();
overwriteCurrentLine(entry.isErr);
return;
}
}


if (ENABLE_SEQUENCE_DETECTION && currentGroupSkeleton != null && detectCycleMatch(skeleton)) {
currentGroupCount.incrementAndGet();
currentGroupLastText = entry.text;
if (ENABLE_SMART_TEMPLATE && currentGroupTemplate != null) {
currentGroupTemplate.merge(entry.text);
}
historyRecord(skeleton, entry.text);
overwriteCurrentLine(entry.isErr);
return;
}


if (ENABLE_BLOCK_DETECTION && currentGroupSkeleton != null && isKnownBlockContinuation(skeleton)) {
currentGroupCount.incrementAndGet();
currentGroupLastText = entry.text;
if (ENABLE_SMART_TEMPLATE && currentGroupTemplate != null) {
currentGroupTemplate.merge(entry.text);
}
historyRecord(skeleton, entry.text);
if (ENABLE_BLOCK_DETECTION) recordBlockSignatures();
overwriteCurrentLine(entry.isErr);
return;
}


if (ENABLE_PREDICTIVE && currentGroupSkeleton == null) {

TemplateState libTmpl = libraryMatch(skeleton);
if (libTmpl != null && isFrequentSkeleton(skeleton)) {

currentGroupSkeleton = skeleton;
currentGroupStructuralTokens = tokens;
currentGroupLastText = entry.text;
currentGroupIsErr = entry.isErr;
currentGroupCount.set(1);
currentGroupTemplate = libTmpl.copy();
currentGroupTemplate.merge(entry.text);
historyRecord(skeleton, entry.text);
if (ENABLE_BLOCK_DETECTION) recordBlockSignatures();
overwriteCurrentLine(entry.isErr);
return;
}
}






if (ENABLE_PREDICTIVE && prevGroupSkeleton != null
&& prevGroupIsErr == entry.isErr
&& isMatchAgainst(skeleton, tokens, prevGroupSkeleton, prevGroupStructuralTokens)) {

finaliseGroup();

currentGroupSkeleton = prevGroupSkeleton;
currentGroupStructuralTokens = prevGroupStructuralTokens;
currentGroupLastText = entry.text;
currentGroupIsErr = entry.isErr;
currentGroupCount.set(prevGroupCount + 1);
if (prevGroupTemplate != null && prevGroupTemplate.valid) {
currentGroupTemplate = prevGroupTemplate;
currentGroupTemplate.merge(entry.text);
} else if (ENABLE_SMART_TEMPLATE) {
currentGroupTemplate = new TemplateState();
currentGroupTemplate.init(entry.text, ENABLE_GRANULAR_TEMPLATE);
}


prevGroupSkeleton = null;
historyRecord(skeleton, entry.text);
if (ENABLE_BLOCK_DETECTION) recordBlockSignatures();
overwriteCurrentLine(entry.isErr);
return;
}


finaliseGroup();


historyRecord(skeleton, entry.text);
if (ENABLE_BLOCK_DETECTION) recordBlockSignatures();

currentGroupSkeleton = skeleton;
currentGroupStructuralTokens = tokens;
currentGroupLastText = entry.text;
currentGroupIsErr = entry.isErr;
currentGroupCount.set(1);


if (ENABLE_SMART_TEMPLATE) {

TemplateState libTmpl = ENABLE_TEMPLATE_LIBRARY ? libraryMatch(skeleton) : null;
if (libTmpl != null) {
currentGroupTemplate = libTmpl.copy();
currentGroupTemplate.merge(entry.text);
} else {
currentGroupTemplate = new TemplateState();
currentGroupTemplate.init(entry.text, ENABLE_GRANULAR_TEMPLATE);
currentGroupTemplate.originSkeleton = skeleton;
}
} else {
currentGroupTemplate = null;
}
overwriteCurrentLine(entry.isErr);
}


private static boolean isMatch(String skeleton, Set<String> tokens) {

if (currentGroupSkeleton.equals(skeleton)) return true;


if (ENABLE_FUZZY && fuzzyMatch(currentGroupStructuralTokens, tokens)) return true;


if (ENABLE_LEVENSHTEIN) {
double levSim = levenshteinSimilarity(currentGroupSkeleton, skeleton);

if (ENABLE_ENTROPY) {
double ent = getEntropy(skeleton);
if (ent >= 0 && ent < 3.0) {
levSim += 0.10;
}
}
if (levSim >= LEVENSHTEIN_THRESHOLD) return true;
}


if (ENABLE_NGRAM) {
double ngramSim = ngramJaccardSimilarity(currentGroupSkeleton, skeleton);
if (ENABLE_ENTROPY) {
double ent = getEntropy(skeleton);
if (ent >= 0 && ent < 3.0) ngramSim += 0.08;
}
if (ngramSim >= NGRAM_THRESHOLD) return true;
}


if (ENABLE_TEMPLATE_LIBRARY) {
TemplateState libGroupTmpl = (currentGroupTemplate != null && currentGroupTemplate.originSkeleton != null)
? templateLibrary.get(currentGroupTemplate.originSkeleton) : null;
TemplateState libNewTmpl = libraryMatch(skeleton);


if (libGroupTmpl != null && libNewTmpl != null
&& libGroupTmpl.originSkeleton != null
&& libGroupTmpl.originSkeleton.equals(libNewTmpl.originSkeleton)) return true;
}

return false;
}


private static boolean isMatchAgainst(String skeleton, Set<String> tokens,
String refSkeleton, Set<String> refTokens) {

if (refSkeleton.equals(skeleton)) return true;

if (ENABLE_FUZZY && fuzzyMatch(refTokens, tokens)) return true;

if (ENABLE_LEVENSHTEIN) {
double sim = levenshteinSimilarity(refSkeleton, skeleton);
if (ENABLE_ENTROPY) {
double ent = getEntropy(skeleton);
if (ent >= 0 && ent < 3.0) sim += 0.10;
}
if (sim >= LEVENSHTEIN_THRESHOLD) return true;
}

if (ENABLE_NGRAM) {
double sim = ngramJaccardSimilarity(refSkeleton, skeleton);
if (ENABLE_ENTROPY) {
double ent = getEntropy(skeleton);
if (ent >= 0 && ent < 3.0) sim += 0.08;
}
if (sim >= NGRAM_THRESHOLD) return true;
}
return false;
}

private static boolean isNeverCollapse(String text) {
return P_NEVER_COLLAPSE.matcher(text).find();
}


private static boolean fuzzyMatch(Set<String> a, Set<String> b) {
if (a == null || b == null) return false;
if (a.isEmpty() && b.isEmpty()) return true;
if (a.isEmpty() || b.isEmpty()) return false;

int minSize = Math.min(a.size(), b.size());
if (minSize == 0) return false;

Set<String> smaller = (a.size() <= b.size()) ? a : b;
Set<String> larger  = (a.size() <= b.size()) ? b : a;
int overlap = 0;
for (String tok : smaller) {
if (larger.contains(tok)) overlap++;
}

return (double) overlap / minSize >= FUZZY_THRESHOLD;
}






static double levenshteinSimilarity(String a, String b) {
if (a == null || b == null) return 0.0;
if (a.equals(b)) return 1.0;
int lenA = a.length(), lenB = b.length();
if (lenA == 0 || lenB == 0) return 0.0;

if (lenA > lenB) { String tmp = a; a = b; b = tmp; int t = lenA; lenA = lenB; lenB = t; }

if (lenA > 500) { a = a.substring(0, 500); lenA = 500; }
if (lenB > 500) { b = b.substring(0, 500); lenB = 500; }
int[] prev = new int[lenA + 1];
int[] curr = new int[lenA + 1];
for (int i = 0; i <= lenA; i++) prev[i] = i;
for (int j = 1; j <= lenB; j++) {
curr[0] = j;
for (int i = 1; i <= lenA; i++) {
int cost = (a.charAt(i - 1) == b.charAt(j - 1)) ? 0 : 1;
curr[i] = Math.min(Math.min(curr[i - 1] + 1, prev[i] + 1), prev[i - 1] + cost);
}
int[] tmp = prev; prev = curr; curr = tmp;
}
int dist = prev[lenA];
return 1.0 - (double) dist / Math.max(lenA, lenB);
}


static double ngramJaccardSimilarity(String a, String b) {
if (a == null || b == null) return 0.0;
if (a.equals(b)) return 1.0;
Set<String> ngramsA = extractNgrams(a, NGRAM_N);
Set<String> ngramsB = extractNgrams(b, NGRAM_N);
if (ngramsA.isEmpty() && ngramsB.isEmpty()) return 1.0;
if (ngramsA.isEmpty() || ngramsB.isEmpty()) return 0.0;
int intersection = 0;
Set<String> smaller = (ngramsA.size() <= ngramsB.size()) ? ngramsA : ngramsB;
Set<String> larger  = (ngramsA.size() <= ngramsB.size()) ? ngramsB : ngramsA;
for (String ng : smaller) {
if (larger.contains(ng)) intersection++;
}
int union = ngramsA.size() + ngramsB.size() - intersection;
return (union == 0) ? 0.0 : (double) intersection / union;
}

private static Set<String> extractNgrams(String s, int n) {

if (s.length() > 500) s = s.substring(0, 500);
Set<String> set = new HashSet<>();
for (int i = 0; i <= s.length() - n; i++) {
set.add(s.substring(i, i + n));
}
return set;
}





private static String buildDisplayText() {
String displayLine;


if (ENABLE_SMART_TEMPLATE && currentGroupTemplate != null
&& currentGroupTemplate.valid && currentGroupCount.get() > 1) {
String tmpl = currentGroupTemplate.toDisplayString();
displayLine = (tmpl != null) ? tmpl : currentGroupLastText;
} else {
displayLine = currentGroupLastText;
}


if (ENABLE_CHAR_FOLDING && displayLine != null
&& displayLine.length() > CHAR_FOLD_VISIBLE_CHARS) {
displayLine = displayLine.substring(0, CHAR_FOLD_VISIBLE_CHARS) + "\u2026";
}

return displayLine;
}

private static void overwriteCurrentLine(boolean isErr) {
PrintStream target = isErr ? REAL_ERR : REAL_OUT;
int count = currentGroupCount.get();

String displayLine = buildDisplayText();

StringBuilder prefixSb = new StringBuilder();
if (count >= MIN_COLLAPSE_DISPLAY) {
prefixSb.append("[x").append(count);
if (ENABLE_SEQUENCE_DETECTION && detectedCyclePeriod > 0 && cycleRepeatCount > 0) {
prefixSb.append(",cyc").append(detectedCyclePeriod);
}
prefixSb.append("] ");
}
String line = prefixSb.toString() + displayLine;

if (line.length() > MAX_OVERWRITE_WIDTH)
line = line.substring(0, MAX_OVERWRITE_WIDTH - 3) + "...";

long prevLen = lastOverwriteLen.get();
int pad = (int) Math.max(0, prevLen - line.length());
StringBuilder sb = new StringBuilder(line.length() + pad + 1);
sb.append('\r').append(line);
for (int i = 0; i < pad; i++) sb.append(' ');

target.print(sb.toString());
target.flush();
lastOverwriteLen.set(line.length());
}

private static void finaliseGroup() {
if (currentGroupSkeleton == null) return;


if (ENABLE_TEMPLATE_LIBRARY && currentGroupTemplate != null
&& currentGroupTemplate.valid && currentGroupCount.get() >= 2) {
librarySave(currentGroupTemplate);
}


if (ENABLE_PREDICTIVE) {
prevGroupSkeleton = currentGroupSkeleton;
prevGroupStructuralTokens = currentGroupStructuralTokens;
prevGroupLastText = currentGroupLastText;
prevGroupIsErr = currentGroupIsErr;
prevGroupCount = currentGroupCount.get();
prevGroupTemplate = (currentGroupTemplate != null && currentGroupTemplate.valid)
? currentGroupTemplate.copy() : null;
}

(currentGroupIsErr ? REAL_ERR : REAL_OUT).println();
(currentGroupIsErr ? REAL_ERR : REAL_OUT).flush();

currentGroupSkeleton = null;
currentGroupStructuralTokens = null;
currentGroupLastText = null;
currentGroupCount.set(0);
currentGroupTemplate = null;
lastOverwriteLen.set(0);
}






static String toSkeleton(String s) {
if (s == null) return "";
s = P_ANSI.matcher(s).replaceAll("");
s = P_SQUOTED.matcher(s).replaceAll("#");
s = P_DQUOTED.matcher(s).replaceAll("#");
s = P_PATH_ABS.matcher(s).replaceAll("#");
s = P_PATH_WIN.matcher(s).replaceAll("#");
s = P_OBJ_HASH.matcher(s).replaceAll("@#");
s = P_HEX.matcher(s).replaceAll("#");
s = P_ID_MIXED.matcher(s).replaceAll("#");
s = P_KV_VALUE.matcher(s).replaceAll("#");
s = P_DIGITS.matcher(s).replaceAll("#");
s = P_MULTISPACE.matcher(s).replaceAll(" ");
return s.trim();
}


static String toSkeletonTimestampAware(String s) {
if (s == null) return "";
s = P_TIMESTAMP_ISO.matcher(s).replaceAll("#TS#");
s = P_TIMESTAMP_TIME.matcher(s).replaceAll("#T#");
s = P_EPOCH_MS.matcher(s).replaceAll("#E#");
return toSkeleton(s);
}


static Set<String> structuralTokens(String s) {
if (s == null || s.isEmpty()) return Collections.emptySet();
String stripped = P_ANSI.matcher(s).replaceAll("");
String[] parts = P_TOKEN_SPLIT.split(stripped.toLowerCase());
Set<String> tokens = new HashSet<>();
for (String p : parts) {
if (p.isEmpty()) continue;
if (P_VARLIKE_TOKEN.matcher(p).matches()) continue;
if (p.length() <= 2) continue;
tokens.add(p);
}
return tokens;
}
}
