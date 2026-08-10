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

import com.company.models.FW;
import com.company.utils.CustomInterceptor2;
import com.company.utils.HibernateSessionFactoryUtil;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;
import org.hibernate.query.Query;

import java.util.ArrayList;
import java.util.List;

public class FWDaoImpl implements FWDao {

private static final Logger log = LogManager.getLogger(FWDaoImpl.class);
private SessionFactory sessionFactory;

@Deprecated
public List<FW> getAllFW() {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions()
.statementInspector(new CustomInterceptor2()).openSession()) {
Query<FW> query = session.createQuery("from FW", FW.class);
return query.list();
}
}

@Override
public void update(FW fw) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor2()).openSession()) {
Transaction tx = session.beginTransaction();
session.merge(fw);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in update", e);
}
}

@Override
public void add(FW fw) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor2()).openSession()) {
Transaction tx = session.beginTransaction();
session.persist(fw);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in add", e);
}
}

@Override
public void addLots(List<FW> fwList) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor2()).openSession()) {
Transaction tx = session.beginTransaction();
for (int i = 0; i < fwList.size(); i++) {
session.persist(fwList.get(i));
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
public void delete(FW fw) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor2()).openSession()) {
Transaction tx = session.beginTransaction();
session.remove(fw);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in delete", e);
}
}

@Override
public FW get(long id) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor2()).openSession()) {
return session.get(FW.class, id);
}
}

@Override
public List<FW> getListOf() {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor2()).openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<FW> criteria = builder.createQuery(FW.class);
Root<FW> root = criteria.from(FW.class);
criteria.select(root);
return session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in getListOf", e);
return new ArrayList<>();
}
}


@Override
public List<FW> getListOf(List<Predicate> predicateList1, List<Predicate> predicateList2) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory()
.withOptions()
.statementInspector(new CustomInterceptor2())
.openSession()) {

CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<FW> criteria = builder.createQuery(FW.class);
Root<FW> root = criteria.from(FW.class);

List<Predicate> combined = new ArrayList<>();
if (predicateList1 != null) combined.addAll(predicateList1);
if (predicateList2 != null) combined.addAll(predicateList2);

if (!combined.isEmpty()) {
criteria.where(combined.toArray(new Predicate[0]));
}

return session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in filtered getListOf with Interceptor", e);
return new ArrayList<>();
}
}

public String getFriendlyName() {
return "FW";
}
}
