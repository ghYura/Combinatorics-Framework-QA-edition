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

import com.company.models.SheetName;
import jakarta.persistence.criteria.Predicate;
import java.util.List;

public interface SheetNameDao extends Dao<SheetName> {
public void update(SheetName t);
public void add(SheetName t);
public void addLots(List<SheetName> t);
public void delete(SheetName t);
public SheetName get(String id);
public List<SheetName> getListOf();
public List<SheetName> getListOf(List<Predicate> t1, List<Predicate> t2);
}
