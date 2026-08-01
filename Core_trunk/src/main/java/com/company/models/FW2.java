package com.company.models;

import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.Arrays;


@Entity
@Table(name = "fw2", schema = "public")
public class FW2 {

@Id
@Column(name = "combi_id")
private long combiId;

@Column(name = "fcombi_id")
private Long fCombiId;


@JdbcTypeCode(SqlTypes.ARRAY)
@Column(name = "combos_1", columnDefinition = "smallint[]")
private short[] combo;

public FW2() {
}

public FW2(long combiId, Long fCombiId) {
this.setCombiId(combiId);
this.setfCombiId(fCombiId);
}

public FW2(long combiId, short[] combo) {
this.setCombiId(combiId);
this.setCombo(combo);
}

@Override
public String toString() {
return Arrays.toString(combo);
}

public long getCombiId()               { return combiId; }
public void setCombiId(long combiId)   { this.combiId = combiId; }

public short[] getCombo()             { return combo; }
public void setCombo(short[] combo)   { this.combo = combo; }

public Long getfCombiId()             { return fCombiId; }
public void setfCombiId(Long fCombiId){ this.fCombiId = fCombiId; }
}
