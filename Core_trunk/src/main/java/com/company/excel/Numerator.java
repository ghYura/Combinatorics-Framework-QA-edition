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

package com.company.excel;

import org.apache.poi.ss.usermodel.Sheet;

import java.io.File;
import java.math.BigInteger;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;



@Deprecated
public class Numerator {
public static int numOfFW_Sheets = 0;
public static short shortSheetNumber = 0;

public static File csvFile = null;
public static File file = null;

public List<Short> lstK2cellV = new ArrayList<>();
public static Map<Short, List<Short>> shortIntSheetK2idxListOfCellK_HM = new LinkedHashMap<>();

public static Map<String, Sheet> stringSheetHM = new LinkedHashMap<>();
public static Map<Short, Sheet> shortSheetHM = new LinkedHashMap<>();
public static Map<Short, String> shortStringSheetKey2SheetNameHM = new LinkedHashMap<>();
public static Map<String, Short> stringShortSheetName2SheetKeyHM = new LinkedHashMap<>();
public static Map<Short, Integer> shortIntegerSheetKey2idxListOfMapsHM = new LinkedHashMap<>();
public static Map<Short, String> shortStringCellValueHM = new LinkedHashMap<>();
public static Map<Short, Short> shortShortDuplicatedCellValueHM = new LinkedHashMap<>();
public static List<Map<Short, String>> shortStringCellValueHMList = new LinkedList<>();

public static String curSheetName;
public static Short curSheetKey;
public static String keyTemp;
public static boolean isOptional;
public static boolean isReuse;
public static Set<Short> reuseSet = new LinkedHashSet<>();
public static boolean isReuseTableOnly;
public static Set<Short> reuseTableOnlySet = new LinkedHashSet<>();
public static boolean isGroup;
public static boolean isJoin;
public static boolean isSeparate;
public static boolean isExclude;
public static boolean isBracketOpen;
public static boolean isBracketClosed;
public static Short keyShortJoin;
public static Short keyShortApply;
public static Short keyShortApply2;
public static Short keyShortExcluded1;
public static List<Short> keyShortExcluded1List = new LinkedList<>();
public static Short keyShortRelation;
public static Short keyShortExcluded2;
public static List<Short> keyShortExcluded2List = new LinkedList<>();
public static Map<String, Integer> stringSheetNameContainsFW_VAR_and_FW_EXIT_CODEMap = new LinkedHashMap<>();
public static Set<String> stringSheetNameContainsFW_VAR_and_FW_EXIT_CODESet = new LinkedHashSet<>();
public static int FW_VAR_and_FW_EXIT_CODEperSheetCounter;
public static Short keyShortSeparate;
public static Short keyShortStart;
public static Short keyShortEnd;
public static Short keyShortBracketOpen;
public static Short keyShortBracketClosed;
public static Map<String, String> replacerHM = new LinkedHashMap();
public static String curStrInCombinations;

public static long k2sOptId = 0L;
public static long fwId = 0L;
public static long fwId2 = 0L;
public static long fComboId = 0L;
public static String curTableName = "fw";
public static int counter4copy = 0;

public static String[] strMasCartessian = null;
public static int counter4cartessian = 0;
public static long counter4cartessianLong = 0L;
public static int cores = Runtime.getRuntime().availableProcessors();
public static List<String> tablespaceList = new ArrayList<>();
public static boolean isWindows = System.getProperty("os.name").matches(".*[Ww]indows.*");
public static String sqlCoreStatic = "";

public static BigInteger counter4maxCombinationOptional = BigInteger.valueOf(0);

public static LinkedHashMap<String, Object> columnNamesFirstRowStaticHM = null;

public static boolean isCombi2 = false;
public static boolean isAppendSqlFiles = false;

public static ConcurrentHashMap<String, String> sharedThreadedHM = new ConcurrentHashMap<>();


public static ConcurrentLinkedQueue<Thread> sharedThreadedQueue = new ConcurrentLinkedQueue<>();
public static ConcurrentLinkedQueue<Thread> sharedThreadedQueueSucceeded = new ConcurrentLinkedQueue<>();
public static ConcurrentHashMap<Short, Boolean> sharedThreadedHMSucceededBoolean = new ConcurrentHashMap<>();
public static ConcurrentLinkedQueue<Thread> sharedThreadedQueueOptional = new ConcurrentLinkedQueue<>();
public static ConcurrentLinkedQueue<Thread> sharedThreadedQueueOptionalSucceeded = new ConcurrentLinkedQueue<>();
public static ConcurrentHashMap<Short, Boolean> sharedThreadedHMOptionalSucceededBoolean = new ConcurrentHashMap<>();

public static Queue<Short> fw_BraceQueue = new PriorityQueue<>();
public static ConcurrentHashMap<Short, Boolean> filledExcludedMap = new ConcurrentHashMap<>();
public static String createSql = "", createSql00 = "";
public static volatile boolean isLaunchedOnce_cleanupAndEraseExcludedTablesThread = false;
public static volatile boolean isLaunchedOnce_mockupPreparationOfSqlFinalTableThread = false;
public static ConcurrentLinkedQueue<String> fwUnderscoreBraceThreadNameQ = new ConcurrentLinkedQueue<>();
public static volatile boolean isFnlThreadInitiated = false, isOptsThreadInitiated = false, isFnlThreadCompleted = false, isOptsThreadCompleted = false;

public static ConcurrentLinkedQueue<Thread> sharedThreadedQueueExcluded = new ConcurrentLinkedQueue<>();
public static ConcurrentLinkedQueue<Thread> sharedThreadedQueueExcludedSucceeded = new ConcurrentLinkedQueue<>();
public static ConcurrentLinkedQueue<Thread> sharedThreadedQueueExcludedOptional = new ConcurrentLinkedQueue<>();
public static ConcurrentLinkedQueue<Thread> sharedThreadedQueueLast = new ConcurrentLinkedQueue<>();
public static ConcurrentLinkedQueue<Thread> sharedThreadedQueueLastOpt = new ConcurrentLinkedQueue<>();

public static ConcurrentLinkedQueue<Thread> threadsOptQ = new ConcurrentLinkedQueue<>();
public static ConcurrentLinkedQueue<Thread> threadsQ = new ConcurrentLinkedQueue<>();
}
