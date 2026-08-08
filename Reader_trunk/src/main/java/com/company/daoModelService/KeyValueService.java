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

import com.company.dao.NumberToValue1DaoImpl;
import com.company.models.NumberToValue1;

import java.util.List;

public class KeyValueService {


private NumberToValue1DaoImpl kvDao = new NumberToValue1DaoImpl();

public KeyValueService() {
}

public void updateKV(NumberToValue1 kv){
kvDao.update(kv);
}

public void addKV(NumberToValue1 kv){
kvDao.add(kv);
}

public void addLotsKV(List<NumberToValue1> kvList) {
kvDao.addLots(kvList);
}

public void deleteKV(NumberToValue1 kv){
kvDao.delete(kv);
}

public NumberToValue1 getKV(short id){


return kvDao.get(id);
}

public List<NumberToValue1> getListOfKVs(){
return kvDao.getListOf();
}


}
