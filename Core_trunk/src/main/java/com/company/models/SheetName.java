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
@Table(name = "names", schema = "public")
public class SheetName {

@Id
@Column(name = "sheet")
private String sheet;

@Column(name = "name")
private String name;

@Column(name = "ending")
private String ending;




public SheetName() {
}

public SheetName(String sheet, String name) {
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
