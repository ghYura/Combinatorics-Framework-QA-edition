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

import com.company.dao.FW_CUSTOM_VARDaoImpl;
import com.company.models.FW_CUSTOM_VAR;

import java.util.List;

public class FW_CUSTOM_VARService {


private FW_CUSTOM_VARDaoImpl fwCustomVarDao = new FW_CUSTOM_VARDaoImpl();

public FW_CUSTOM_VARService() {
}

public void updateFW_CUSTOM_VAR(FW_CUSTOM_VAR fwCustomVar){
fwCustomVarDao.update(fwCustomVar);
}

public void addFW_CUSTOM_VAR(FW_CUSTOM_VAR fwCustomVar){
fwCustomVarDao.add(fwCustomVar);
}

public void addLotsFW_CUSTOM_VAR(List<FW_CUSTOM_VAR> fwCustomVarList) {
fwCustomVarDao.addLots(fwCustomVarList);
}

public void deleteFW_CUSTOM_VAR(FW_CUSTOM_VAR fwCustomVar){
fwCustomVarDao.delete(fwCustomVar);
}

public FW_CUSTOM_VAR getFW_CUSTOM_VAR(Integer fwCustomVar){
return fwCustomVarDao.get(fwCustomVar);
}

public List<FW_CUSTOM_VAR> getListOfFW_CUSTOM_VARs(){
return fwCustomVarDao.getListOf();
}


}
