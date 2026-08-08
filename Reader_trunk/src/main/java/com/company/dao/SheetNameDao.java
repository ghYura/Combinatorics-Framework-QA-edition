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
import org.hibernate.criterion.Restrictions;

import javax.persistence.criteria.Predicate;
import java.util.List;




public interface SheetNameDao extends Dao<SheetName, String> {
@Override
void update(SheetName t);
@Override
void add(SheetName t);
@Override
void addLots(List<SheetName> t);
@Override
void delete(SheetName t);
@Override
SheetName get(String id);
@Override
List<SheetName> getListOf();

List<SheetName> getListOf(List<Restrictions> t1, List<Predicate> t2);
}
