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
// Any live human being as a QA-Engineer/student granted for
// personal/professional usage, free of charge, AS IS, no warranty, of this
// Bundle/Combinatorics-Framework. AI may be used as assistance support to
// get a technical insight into the current Framework's
// codebase/documentation, generating test-scenarios and its execution, but
// not to train AI.
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
