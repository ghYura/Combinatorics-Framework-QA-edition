package com.company.daoModelService;

import com.company.dao.SheetNameDaoImpl;
import com.company.models.SheetName;

import java.util.List;

public class SheetNameService {


private SheetNameDaoImpl sheetNameDao = new SheetNameDaoImpl();

public SheetNameService() {
}

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
