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
