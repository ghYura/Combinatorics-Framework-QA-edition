package com.company.models;


import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customvarmap", schema = "public")
public class FW_CUSTOM_VAR {

@Id
@Column(name = "fw_custom_var")
private Integer fwCustomVar;

@Column(name = "message")
private String message;


public FW_CUSTOM_VAR(){ }

public FW_CUSTOM_VAR(Integer fwCustomVar, String message){
this.setFwCustomVar(fwCustomVar);
this.setMessage(message);
}

public Integer getFwCustomVar() {
return fwCustomVar;
}

public void setFwCustomVar(Integer fwCustomVar) {
this.fwCustomVar = fwCustomVar;
}

public String getMessage() {
return message;
}

public void setMessage(String message) {
this.message = message;
}
}
