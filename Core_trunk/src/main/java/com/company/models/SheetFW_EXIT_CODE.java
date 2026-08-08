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


import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;


@Entity
@Table(name = "\"ColumnsContainFwExitCode\"", schema = "public")
public class SheetFW_EXIT_CODE {

@Id
@Column(name = "sheet")
private String sheet;

@Column(name = "fw_exit_code")
private Integer FW_EXIT_CODE;

@Column(name = "count_per_sheet")
private int FW_VAR_and_FW_EXIT_CODEperSheetCounter;

public SheetFW_EXIT_CODE() {
}

public SheetFW_EXIT_CODE(String sheet) {
this.setSheet(sheet);
}

public String getSheet() {
return sheet;
}

public void setSheet(String sheet) {
this.sheet = sheet;
}

public Integer getFW_EXIT_CODE() {
return FW_EXIT_CODE;
}

public void setFW_EXIT_CODE(Integer FW_EXIT_CODE) {
this.FW_EXIT_CODE = FW_EXIT_CODE;
}

public int getFW_VAR_and_FW_EXIT_CODEperSheetCounter() {
return FW_VAR_and_FW_EXIT_CODEperSheetCounter;
}

public void setFW_VAR_and_FW_EXIT_CODEperSheetCounter(int FW_VAR_and_FW_EXIT_CODEperSheetCounter) {
this.FW_VAR_and_FW_EXIT_CODEperSheetCounter = FW_VAR_and_FW_EXIT_CODEperSheetCounter;
}
}
