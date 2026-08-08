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

import com.company.dao.ComboKey2SheetOptionalDaoImpl;
import com.company.models.ComboKey2SheetOptional;

import java.util.List;

public class ComboK2SOptService {


private ComboKey2SheetOptionalDaoImpl comboKOptDao = new ComboKey2SheetOptionalDaoImpl();

public ComboK2SOptService() {
}

public void updateComboK2SOpt(ComboKey2SheetOptional comboKOpt){
comboKOptDao.update(comboKOpt);
}


public void addArrArrComboK2SOpt(ComboKey2SheetOptional comboKOpt){
comboKOptDao.addArrArr(comboKOpt);
}

public void addComboK2SOpt(ComboKey2SheetOptional comboKOpt){
comboKOptDao.add(comboKOpt);
}

public void addLotsComboK2SOpt(List<ComboKey2SheetOptional> comboKOptList) {
comboKOptDao.addLots(comboKOptList);
}

public void deleteComboK2SOpt(ComboKey2SheetOptional comboKOpt){
comboKOptDao.delete(comboKOpt);
}

public ComboKey2SheetOptional getComboKOpt(long id){
return comboKOptDao.get(id);
}

public List<ComboKey2SheetOptional> getListOfcombosKOpt(){
return comboKOptDao.getListOf();
}
}
