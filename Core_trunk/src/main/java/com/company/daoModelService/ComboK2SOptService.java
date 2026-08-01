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
