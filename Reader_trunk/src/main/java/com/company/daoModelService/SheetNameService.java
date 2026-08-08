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

package com.company.daoModelService;

import com.company.dao.SheetNameDaoImpl;
import com.company.models.SheetName;

import java.util.List;

public class SheetNameService {


private SheetNameDaoImpl sheetNameDao = new SheetNameDaoImpl();

public SheetNameService() {}

public void updateSheetName(SheetName sheetName){
sheetNameDao.update(sheetName);
}

public void addSheetName(SheetName sheetName){
sheetNameDao.add(sheetName);
}

public void addLotsSheetName(List<SheetName> sheetNameList) {
sheetNameDao.addLots(sheetNameList);
}

public void deleteSheetName(SheetName sheetName){
sheetNameDao.delete(sheetName);
}

public SheetName getSheetName(String sheet){
return sheetNameDao.get(sheet);
}

public List<SheetName> getListOfSheetNames(){
return sheetNameDao.getListOf();
}

}
