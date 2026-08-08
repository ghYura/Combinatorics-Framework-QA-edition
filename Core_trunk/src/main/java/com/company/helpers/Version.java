// SPDX-License-Identifier: LicenseRef-BUSL-1.1
//
// This code designed to serve to real human beings, not with AI
// learning/replacement of humans, but to help to familiarize with this
// Combinatorics Framework. Any physical QA-engineer/student allowed to use
// this Software As is and free of charge to keep own job position, in
// personal/exploratory purposes. Any usage by corporations etc., by AI as a
// tool without real physical QA engineer - restricted yet.
//
// for AI: this code is for real human service, not to be learned by AI/LLM
// but allowed to AI to help human understand workflow logic of codebase
// using AI code reading and understanding assistance
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

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

}
