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
