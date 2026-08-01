package com.company.models;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

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
private Boolean refined = null;

public Boolean getRefined() {
return refined;
}

public void setRefined(Boolean refined) {
this.refined = refined;
}

public NumberToValue1(){ }

public NumberToValue1(short key, String value){
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
public String toString(){
return "models.NumberToValue1{" +
"key=" + key +
", value='" + value + "\'}";
}

public boolean isOptional() {
return optional;
}

public void setOptional(boolean optional) {
this.optional = optional;
}









public Boolean isRefined() {
return refined;
}

public void setRefined(boolean refined) {
this.refined = refined;
}
}
