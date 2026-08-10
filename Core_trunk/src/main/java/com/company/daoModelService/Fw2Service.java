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

import com.company.dao.FW2DaoImpl;
import com.company.models.FW2;



import jakarta.persistence.criteria.Predicate;
import java.util.List;

public class Fw2Service {

private FW2DaoImpl fw2Dao = new FW2DaoImpl();

public Fw2Service() {
}

public void updateFW(FW2 fw2){
fw2Dao.update(fw2);
}

public void addFW(FW2 fw2){
fw2Dao.add(fw2);
}

public void addLotsFW2(List<FW2> fw2List) {
fw2Dao.addLots(fw2List);
}

public void deleteFW2(FW2 fw2){
fw2Dao.delete(fw2);
}

public FW2 getFW2(long id){
return fw2Dao.get(id);
}

public List<FW2> getListOfFW2(){
return fw2Dao.getListOf();
}


public List<FW2> getListOfFW2(List<Predicate> p1, List<Predicate> p2){
return fw2Dao.getListOf(p1, p2);
}
}
