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
