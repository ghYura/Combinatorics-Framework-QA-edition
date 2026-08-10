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

package com.company.daoModelService;

import com.company.dao.SheetFW_EXIT_CODEDaoImpl;
import com.company.models.SheetFW_EXIT_CODE;

import java.util.List;

public class SheetFW_EXIT_CODEService {


private SheetFW_EXIT_CODEDaoImpl sheetFW_EXIT_CODEDao = new SheetFW_EXIT_CODEDaoImpl();

public SheetFW_EXIT_CODEService() {
}

public void updateSheetFW_EXIT_CODE(SheetFW_EXIT_CODE sheetFW_EXIT_CODE){
sheetFW_EXIT_CODEDao.update(sheetFW_EXIT_CODE);
}

public void addSheetFW_EXIT_CODE(SheetFW_EXIT_CODE sheetFW_EXIT_CODE){
sheetFW_EXIT_CODEDao.add(sheetFW_EXIT_CODE);
}

public void addLotsSheetFW_EXIT_CODE(List<SheetFW_EXIT_CODE> sheetFW_EXIT_CODEList) {
sheetFW_EXIT_CODEDao.addLots(sheetFW_EXIT_CODEList);
}

public void deleteSheetFW_EXIT_CODE(SheetFW_EXIT_CODE sheetFW_EXIT_CODE){
sheetFW_EXIT_CODEDao.delete(sheetFW_EXIT_CODE);
}

public SheetFW_EXIT_CODE getSheetFW_EXIT_CODE(String sheet){
return sheetFW_EXIT_CODEDao.get(sheet);
}

public List<SheetFW_EXIT_CODE> getListOfSheetFW_EXIT_CODEs(){
return sheetFW_EXIT_CODEDao.getListOf();
}


}
