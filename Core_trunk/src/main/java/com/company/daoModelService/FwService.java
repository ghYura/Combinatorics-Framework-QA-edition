package com.company.daoModelService;

import com.company.dao.FWDaoImpl;
import com.company.models.FW;
import jakarta.persistence.criteria.Predicate;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;
import java.util.stream.Collectors;


public class FwService {


private final AtomicReference<Map<Long, FW>> mapFWRef = new AtomicReference<>(null);


private volatile List<FW> listFW = null;

private final FWDaoImpl fwDao = new FWDaoImpl();

public FwService() { }



public void updateFW(FW fw) {
fwDao.update(fw);
}

public void addFW(FW fw) {
fwDao.add(fw);
}

public void addLotsFW(List<FW> fwList) {
fwDao.addLots(fwList);
}

public void deleteFW(FW fw) {
fwDao.delete(fw);
}



public FW getFW(long id) {
return fwDao.get(id);
}

public List<FW> getListOfFW() {
return fwDao.getListOf();
}


public List<FW> getListOfFW(List<Predicate> p1, List<Predicate> p2) {

return fwDao.getListOf(p1, p2);
}




public FW getFWfromPreloadedList(long id) {

return getFWfromPreloadedMap(id);
}


public FW getFWfromPreloadedMap(long id) {
var map = mapFWRef.get();
if (map == null) {
var loaded = getMapOfFW();
if (!mapFWRef.compareAndSet(null, loaded)) {

map = mapFWRef.get();
} else {
map = loaded;
}
}
return (map != null) ? map.get(id) : null;
}


public Map<Long, FW> getMapOfFW() {
var list = getListOfFW();
return list.stream().collect(
Collectors.toMap(FW::getCombiId, Function.identity()));
}




public void clearAllDataInFWserviceObject() {
mapFWRef.set(null);
listFW = null;
}




@Deprecated
@SuppressWarnings("unused")
private FW getFWfromPreloadedList_LEGACY(long id) {
boolean reachEnd   = false;
boolean reachBegin = false;
if (listFW == null) listFW = getListOfFW();
var curFW  = new FW();
var curFWb = new FW();
if (listFW != null && !listFW.isEmpty()) {
var iter  = listFW.listIterator();
var iterb = listFW.listIterator();
if (iter.hasNext()) curFW = iter.next();
loop1:
while (!reachEnd || curFW.getCombiId() != id) {
if (iter.hasNext()) {
curFW = iter.next();
iterb = listFW.listIterator(iter.nextIndex());
loop2:
while (!reachBegin || curFWb.getCombiId() != id) {
if (iterb.hasPrevious()) curFWb = iterb.previous();
if (!iterb.hasPrevious()) reachBegin = true;
if (curFWb.getCombiId() == id || curFW.getCombiId() == id) break loop2;
}
}
if (!iter.hasNext()) reachEnd = true;
if (curFW.getCombiId() == id || curFWb.getCombiId() == id) break loop1;
}
}
if (curFW.getCombiId() == id)  return curFW;
if (curFWb.getCombiId() == id) return curFWb;
return null;
}
}
