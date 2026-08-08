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

import com.company.helpers.CodeLineNumber;
import com.company.models.SheetName;
import com.company.utils.HibernateSessionFactoryUtil;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.hibernate.Session;
import org.hibernate.Transaction;

import java.util.ArrayList;
import java.util.List;

public class SheetNameDaoImpl implements SheetNameDao {

private static final Logger log = LogManager.getLogger(SheetNameDaoImpl.class);

@Override
public void update(SheetName sheetName) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.merge(sheetName);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in update", e);
}
}

@Override
public void add(SheetName sheetName) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
try {
session.persist(sheetName);
} catch (org.hibernate.id.IdentifierGenerationException hibernExc) {
log.warn("[REFACTOR9] IdentifierGenerationException (line {}): {}",
CodeLineNumber.getLineNumber(), hibernExc.getMessage());
}
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in add", e);
}
}

@Override
public void addLots(List<SheetName> sheetNameList) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
for (int i = 0; i < sheetNameList.size(); i++) {
session.persist(sheetNameList.get(i));
if (i % 500 == 0) {
session.flush();
session.clear();
}
}
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in addLots", e);
}
}

@Override
public void delete(SheetName sheetName) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.remove(sheetName);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in delete", e);
}
}

@Override
public SheetName get(long id) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
return session.get(SheetName.class, id);
}
}

@Override
public SheetName get(String sheet) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
return session.get(SheetName.class, sheet);
} catch (Exception e) {
log.error("[REFACTOR9] Exception in get(String)", e);
return null;
}
}

@Override
public List<SheetName> getListOf() {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<SheetName> criteria = builder.createQuery(SheetName.class);
Root<SheetName> root = criteria.from(SheetName.class);
criteria.select(root);
return session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in getListOf", e);
return new ArrayList<>();
}
}


@Override
public List<SheetName> getListOf(List<Predicate> t1, List<Predicate> t2) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<SheetName> criteria = builder.createQuery(SheetName.class);
Root<SheetName> root = criteria.from(SheetName.class);

List<Predicate> combined = new ArrayList<>();
if (t1 != null) combined.addAll(t1);
if (t2 != null) combined.addAll(t2);

if (!combined.isEmpty()) {
criteria.where(combined.toArray(new Predicate[0]));
}

return session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in filtered getListOf", e);
return new ArrayList<>();
}
}

public String getFriendlyName() {
return "SheetName";
}
}
