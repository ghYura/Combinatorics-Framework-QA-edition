package com.company.models;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "names", schema = "public")
public class SheetName {

@Id
@Column(name = "sheet")
private String sheet;
@Column(name = "name")
private String name;
@Column(name = "ending")
private String ending;



public SheetName(){ }

public SheetName(String sheet, String name){
this.setSheet(sheet);
this.setName(name);
}


public String getSheet() {
return sheet;
}

public void setSheet(String sheet) {
this.sheet = sheet;
}

public String getName() {
return name;
}

public void setName(String name) {
this.name = name;
}

public String getEnding() {
return ending;
}

public void setEnding(String ending) {
this.ending = ending;
}








}
