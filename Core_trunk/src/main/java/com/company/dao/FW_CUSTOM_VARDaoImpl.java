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

package com.company.dao;

import com.company.models.FW_CUSTOM_VAR;
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

public class FW_CUSTOM_VARDaoImpl implements FW_CUSTOM_VARDao {

private static final Logger log = LogManager.getLogger(FW_CUSTOM_VARDaoImpl.class);



@Override
public void update(FW_CUSTOM_VAR fwCustomVar) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.merge(fwCustomVar);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Update failed", e);
}
}

@Override
public void add(FW_CUSTOM_VAR fwCustomVar) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.persist(fwCustomVar);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Add failed", e);
}
}

@Override
public void addLots(List<FW_CUSTOM_VAR> fwCustomVarsList) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
for (int i = 0; i < fwCustomVarsList.size(); i++) {
session.persist(fwCustomVarsList.get(i));
if (i % 500 == 0) {
session.flush();
session.clear();
}
}
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] AddLots failed", e);
}
}

@Override
public void delete(FW_CUSTOM_VAR fwCustomVar) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.remove(fwCustomVar);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Delete failed", e);
}
}




@Override
public FW_CUSTOM_VAR get(long id) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
return session.get(FW_CUSTOM_VAR.class, id);
}
}


@Override
public FW_CUSTOM_VAR get(Integer id) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
return session.get(FW_CUSTOM_VAR.class, id);
} catch (Exception e) {
log.error("[REFACTOR9] get(Integer) failed", e);
return null;
}
}



@Override
public List<FW_CUSTOM_VAR> getListOf() {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<FW_CUSTOM_VAR> criteria = builder.createQuery(FW_CUSTOM_VAR.class);
Root<FW_CUSTOM_VAR> root = criteria.from(FW_CUSTOM_VAR.class);
criteria.select(root);
return session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR9] getListOf failed", e);
return new ArrayList<>();
}
}

@Override
public List<FW_CUSTOM_VAR> getListOf(List<Predicate> t1, List<Predicate> t2) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<FW_CUSTOM_VAR> criteria = builder.createQuery(FW_CUSTOM_VAR.class);
Root<FW_CUSTOM_VAR> root = criteria.from(FW_CUSTOM_VAR.class);

List<Predicate> combined = new ArrayList<>();
if (t1 != null) combined.addAll(t1);
if (t2 != null) combined.addAll(t2);

if (!combined.isEmpty()) {
criteria.where(combined.toArray(new Predicate[0]));
}
return session.createQuery(criteria).getResultList();
}
}

public String getFriendlyName() {
return "FW_CUSTOM_VAR";
}
}
