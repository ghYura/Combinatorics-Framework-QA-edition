package com.company.helpers;

import com.company.PrintPretty;

public class Version implements Comparable<Version> {

private String version;

public final String get() {
return this.version;
}


public Version(String version) {

if(version == null)
version = "5.2.12";
if(!version.matches("[0-9]+(\\.[0-9]+)*"))
throw new IllegalArgumentException("Invalid version format");
this.version = version;
}

@Override public int compareTo(Version that) {
if(that == null)
return 1;
String[] thisParts = this.get().split("\\.");
String[] thatParts = that.get().split("\\.");
int length = Math.max(thisParts.length, thatParts.length);
for(int i = 0; i < length; i++) {
int thisPart = i < thisParts.length ?
Integer.parseInt(thisParts[i]) : 0;
int thatPart = i < thatParts.length ?
Integer.parseInt(thatParts[i]) : 0;
if(thisPart < thatPart)
return -1;
if(thisPart > thatPart)
return 1;
}
return 0;
}

@Override public boolean equals(Object that) {
if(this == that)
return true;
if(that == null)
return false;
if(this.getClass() != that.getClass())
return false;
return this.compareTo((Version) that) == 0;
}






@Override public int hashCode() {
if (version == null) return 0;
String[] parts = version.split("\\.");
int end = parts.length;
while (end > 0) {
try {
if (Integer.parseInt(parts[end - 1]) == 0) { end--; continue; }
} catch (NumberFormatException e) {  }
break;
}
int h = 1;
for (int i = 0; i < end; i++) {
try {
h = 31 * h + Integer.parseInt(parts[i]);
} catch (NumberFormatException e) {
h = 31 * h + parts[i].hashCode();
}
}
return h;
}

}
