package com.company.models;



import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.Column;




@MappedSuperclass
public class BaseEntity {

@Id
@Column(name = "combi_id")
private Long combiId;

@Column(name = "combo_txt")
private String comboString;

private Long fCombiId;

public BaseEntity() {
}

public Long getCombiId() {
return combiId;
}

public void setCombiId(Long combiId) {
this.combiId = combiId;
}

public String getComboString() {
return comboString;
}

public void setComboString(String comboString) {
this.comboString = comboString;
}

public Long getfCombiId() {
return fCombiId;
}

public void setfCombiId(Long fCombiId) {
this.fCombiId = fCombiId;
}
}
