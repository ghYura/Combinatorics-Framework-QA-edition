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
