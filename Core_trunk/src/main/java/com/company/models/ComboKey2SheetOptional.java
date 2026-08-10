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
