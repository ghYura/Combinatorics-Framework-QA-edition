package com.company.helpers;

import com.google.common.math.LongMath;

import java.math.RoundingMode;
import java.util.LinkedHashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;

public class Chunker {

public Chunker(){}

public static Map<String, List<Map.Entry<Long, Long>>> chunk(List<Long> listOfLongs, List<String> listOfStrings, long chunkDelta){
Map<String, List<Map.Entry<Long, Long>>> mapOfString2ListsOfEntries = new LinkedHashMap<>();
int counterTables = 0;
for (Long curr : listOfLongs){
List<Map.Entry<Long, Long>> list = new LinkedList<>();
long counter = 0L;
long cur1 = 1L;
long cur2 = 1L;
Map<Long, Long> map = new LinkedHashMap<>();
while (counter <= LongMath.divide(curr, chunkDelta, RoundingMode.HALF_DOWN)) {
cur2 = cur1 + chunkDelta;
map.put(cur1, cur2);
list.add(((LinkedHashMap<Long, Long>) ((LinkedHashMap<Long, Long>) map).clone()).entrySet().iterator().next());
cur1 = cur2 + 1L;
counter = counter + 1L;
map.clear();
}
mapOfString2ListsOfEntries.put(listOfStrings.get(counterTables), list);
counterTables++;
}

return mapOfString2ListsOfEntries;
}
}
