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
