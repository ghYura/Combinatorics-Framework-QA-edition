package com.company.models;

import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.Arrays;


@Entity
@Table(name = "fw", schema = "public")
public class FW {

@Id
@Column(name = "combi_id")
private long combiId;

@Column(name = "combo_txt")
private String comboString;


@JdbcTypeCode(SqlTypes.ARRAY)
@Column(name = "combos", columnDefinition = "integer[]")
private int[] combo;

public FW() {
}

public FW(long combiId, String comboString) {
this.setCombiId(combiId);
this.setComboString(comboString);
}

public FW(long combiId, int[] combo) {
this.setCombiId(combiId);
this.setCombo(combo);
}

@Override
public String toString() {
return Arrays.toString(combo);
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
