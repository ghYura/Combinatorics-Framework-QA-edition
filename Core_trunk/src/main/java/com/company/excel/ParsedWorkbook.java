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

package com.company.excel;

import org.apache.poi.ss.usermodel.Sheet;

import java.util.*;


public final class ParsedWorkbook {




public final Map<Short, Sheet> shortSheetHM;


public final Map<String, Sheet> stringSheetHM;




public final Map<Short, String> shortStringSheetKey2SheetNameHM;


public final Map<String, Short> stringShortSheetName2SheetKeyHM;




public final Map<Short, String> shortStringCellValueHM;


public final Map<Short, List<Short>> shortIntSheetK2idxListOfCellK_HM;




public final Map<Short, List<Short>> sheetData;




public final int numOfFwSheets;


public final short maxSheetNumber;



public final Set<String> virtualSheetNames;


public final Map<Integer, Short> fwSeqRowSyntheticTarget;




private ParsedWorkbook(Builder b) {
this.shortSheetHM                      = Collections.unmodifiableMap(new LinkedHashMap<>(b.shortSheetHM));
this.stringSheetHM                     = Collections.unmodifiableMap(new LinkedHashMap<>(b.stringSheetHM));
this.shortStringSheetKey2SheetNameHM   = Collections.unmodifiableMap(new LinkedHashMap<>(b.key2name));
this.stringShortSheetName2SheetKeyHM   = Collections.unmodifiableMap(new LinkedHashMap<>(b.name2key));
this.shortStringCellValueHM            = Collections.unmodifiableMap(new LinkedHashMap<>(b.shortStringCellValueHM));
this.shortIntSheetK2idxListOfCellK_HM  = Collections.unmodifiableMap(new LinkedHashMap<>(b.shortIntSheetK2idxListOfCellK_HM));
this.sheetData                         = Collections.unmodifiableMap(new LinkedHashMap<>(b.sheetData));
this.numOfFwSheets                     = b.numOfFwSheets;
this.maxSheetNumber                    = b.maxSheetNumber;

this.virtualSheetNames                 = Collections.unmodifiableSet(new LinkedHashSet<>(b.virtualSheetNames));
this.fwSeqRowSyntheticTarget           = Collections.unmodifiableMap(new LinkedHashMap<>(b.fwSeqRowSyntheticTarget));

}



static final class Builder {
final Map<Short, Sheet>        shortSheetHM                     = new LinkedHashMap<>();
final Map<String, Sheet>       stringSheetHM                    = new LinkedHashMap<>();
final Map<Short, String>       key2name                         = new LinkedHashMap<>();
final Map<String, Short>       name2key                         = new LinkedHashMap<>();
final Map<Short, String>       shortStringCellValueHM           = new LinkedHashMap<>();
final Map<Short, List<Short>>  shortIntSheetK2idxListOfCellK_HM = new LinkedHashMap<>();
final Map<Short, List<Short>>  sheetData                        = new LinkedHashMap<>();

final Set<String>              virtualSheetNames                = new LinkedHashSet<>();
final Map<Integer, Short>      fwSeqRowSyntheticTarget          = new LinkedHashMap<>();


int   numOfFwSheets  = 0;
short maxSheetNumber = 0;

ParsedWorkbook build() {
return new ParsedWorkbook(this);
}



short registerVirtualSheet(String name) {
maxSheetNumber = (short) (maxSheetNumber + 1);
key2name.put(maxSheetNumber, name);
name2key.put(name, maxSheetNumber);
sheetData.put(maxSheetNumber, new java.util.ArrayList<>());
virtualSheetNames.add(name);
return maxSheetNumber;
}

}
}
