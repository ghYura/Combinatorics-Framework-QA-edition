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
