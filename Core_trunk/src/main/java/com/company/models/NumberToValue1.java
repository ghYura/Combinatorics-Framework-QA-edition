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

package com.company.models;


import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "\"NumberToValue1\"", schema = "public")
public class NumberToValue1 {

@Id
@Column(name = "bigint")
private short key;

@Column(name = "value")
private String value;

@Column(name = "optional")
private boolean optional;


@Column(name = "refined")
private boolean refined = false;

public NumberToValue1() {
}

public NumberToValue1(short key, String value) {
this.setKey(key);
this.setValue(value);
}

public short getKey() {
return key;
}

public void setKey(short key) {
this.key = key;
}

public String getValue() {
return value;
}

public void setValue(String value) {
this.value = value;
}

@Override
public String toString() {
return "models.NumberToValue1{" +
"key=" + key +
", value='" + value + "'}";
}

public boolean isOptional() {
return optional;
}

public void setOptional(boolean optional) {
this.optional = optional;
}

public boolean isRefined() {
return refined;
}

public void setRefined(boolean refined) {
this.refined = refined;
}
}
