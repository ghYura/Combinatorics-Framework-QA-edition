package com.company;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

public class FinalOptMapOfComb {

public FinalOptMapOfComb(){}

public FinalOptMapOfComb(Long finalLong, Long optLong, Map<Integer, short[]> mapOfComb1, Map<Integer, short[]> mapOfComb2){
this.setFinalLong(finalLong);
this.setOptLong(optLong);
this.setMapOfComb1(mapOfComb1);
this.setMapOfComb2(mapOfComb2);
}

private Long finalLong = null;
private Long optLong = null;
private Map<Integer, short[]> mapOfComb1 = new LinkedHashMap<>();
private Map<Integer, short[]> mapOfComb2 = new LinkedHashMap<>();
private Map<Integer, short[]> mapMerged = new LinkedHashMap<>();

public Long getFinalLong() {
return finalLong;
}

public void setFinalLong(Long finalLong) {
this.finalLong = finalLong;
}

public Long getOptLong() {
return optLong;
}

public void setOptLong(Long optLong) {
this.optLong = optLong;
}

public Map<Integer, short[]> getMapOfComb1() {
return mapOfComb1;
}

public void setMapOfComb1(Map<Integer, short[]> mapOfComb1) {
this.mapOfComb1 = mapOfComb1;
}

public Map<Integer, short[]> getMapOfComb2() {
return mapOfComb2;
}

public void setMapOfComb2(Map<Integer, short[]> mapOfComb2) {
this.mapOfComb2 = mapOfComb2;
}

public Map<Integer, short[]> getMergedMap(){
if (mapMerged.isEmpty()) {

if (mapOfComb1 != null) mapMerged.putAll(mapOfComb1);
if (mapOfComb2 != null) mapMerged.putAll(mapOfComb2);
}

return mapMerged;
}

public Map<Map, Map<Integer, short[]>> getFinalOptMapKey2mrgdMapValues(){
Map map = new HashMap();
map.put(finalLong, optLong);
Map<Map, Map<Integer, short[]>> p = new LinkedHashMap<>();
p.put(map, getMergedMap());

return p;
}
}
