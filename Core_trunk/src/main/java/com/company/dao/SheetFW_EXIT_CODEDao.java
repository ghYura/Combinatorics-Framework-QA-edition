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

package com.company.dao;

import com.company.models.SheetFW_EXIT_CODE;
import jakarta.persistence.criteria.Predicate;
import java.util.List;

public interface SheetFW_EXIT_CODEDao extends Dao<SheetFW_EXIT_CODE> {
public void update(SheetFW_EXIT_CODE t);
public void add(SheetFW_EXIT_CODE t);
public void addLots(List<SheetFW_EXIT_CODE> t);
public void delete(SheetFW_EXIT_CODE t);
public SheetFW_EXIT_CODE get(String id);
public List<SheetFW_EXIT_CODE> getListOf();
public List<SheetFW_EXIT_CODE> getListOf(List<Predicate> t1, List<Predicate> t2);
}
