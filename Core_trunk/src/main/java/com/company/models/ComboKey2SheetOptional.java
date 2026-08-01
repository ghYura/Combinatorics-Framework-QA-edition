package com.company.models;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "combokeys2sheetsoptional", schema = "public")
public class ComboKey2SheetOptional {

@Id
@Column(name = "combi_id")
private long combiId;

@Column(name = "combo_txt")
private String comboString;





@Column(name = "combos", columnDefinition = "integer[]")
private int[] combo;

public ComboKey2SheetOptional() {
}

public ComboKey2SheetOptional(long combiId, String comboString) {
this.setCombiId(combiId);
this.setComboString(comboString);
}

public ComboKey2SheetOptional(long combiId, int[] combo) {
this.setCombiId(combiId);
this.setCombo(combo);
}

@Override
public String toString() {
return "models.ComboKey2SheetOptional{" +
"combiId=" + combiId +
", comboString='" + comboString + "\'}";
}

public long getCombiId() {
return combiId;
}

public void setCombiId(long combiId) {
this.combiId = combiId;
}

public String getComboString() {
return comboString;
}

public void setComboString(String comboString) {
this.comboString = comboString;
}

public int[] getCombo() {
return combo;
}

public void setCombo(int[] combo) {
this.combo = combo;
}
}
