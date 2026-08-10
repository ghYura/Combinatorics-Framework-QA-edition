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
@Table(name = "customvarmap", schema = "public")
public class FW_CUSTOM_VAR {

@Id
@Column(name = "fw_custom_var")
private Integer fwCustomVar;

@Column(name = "message")
private String message;


public FW_CUSTOM_VAR(){ }

public FW_CUSTOM_VAR(Integer fwCustomVar, String message){
this.setFwCustomVar(fwCustomVar);
this.setMessage(message);
}

public Integer getFwCustomVar() {
return fwCustomVar;
}

public void setFwCustomVar(Integer fwCustomVar) {
this.fwCustomVar = fwCustomVar;
}

public String getMessage() {
return message;
}

public void setMessage(String message) {
this.message = message;
}
}
