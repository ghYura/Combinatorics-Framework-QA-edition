package com.company.models;

import org.hibernate.annotations.TypeDef;
import org.hibernate.annotations.TypeDefs;

import javax.persistence.Id;
import javax.persistence.MappedSuperclass;

@TypeDefs({
@TypeDef(
name = "int-array",
typeClass = IntArrayType.class
)
})
@MappedSuperclass
public class BaseEntity {

@Id
private Long combiId;

private String comboString;

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
}
