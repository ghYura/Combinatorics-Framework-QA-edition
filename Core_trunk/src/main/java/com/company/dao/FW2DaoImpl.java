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

import com.company.models.FW2;
import com.company.utils.CustomInterceptor22;
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

public class FW2DaoImpl implements FW2Dao {

private static final Logger log = LogManager.getLogger(FW2DaoImpl.class);
private SessionFactory sessionFactory;

@Deprecated
public List<FW2> getAllFW2() {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions()
.statementInspector(new CustomInterceptor22()).openSession()) {
Query<FW2> query = session.createQuery("from FW2", FW2.class);
return query.list();
}
}

@Override
public void update(FW2 fw2) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor22()).openSession()) {
Transaction tx = session.beginTransaction();
session.merge(fw2);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Update failed", e);
}
}

@Override
public void add(FW2 fw2) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor22()).openSession()) {
Transaction tx = session.beginTransaction();
session.persist(fw2);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Add failed", e);
}
}

@Override
public void addLots(List<FW2> fw2List) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor22()).openSession()) {
Transaction tx = session.beginTransaction();
for (int i = 0; i < fw2List.size(); i++) {
session.persist(fw2List.get(i));
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
public void delete(FW2 fw2) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor22()).openSession()) {
Transaction tx = session.beginTransaction();
session.remove(fw2);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Delete failed", e);
}
}

@Override
public FW2 get(long id) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor22()).openSession()) {
return session.get(FW2.class, id);
}
}

@Override
public List<FW2> getListOf() {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().withOptions().statementInspector(new CustomInterceptor22()).openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<FW2> criteria = builder.createQuery(FW2.class);
Root<FW2> root = criteria.from(FW2.class);
criteria.select(root);
return session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR9] getListOf failed", e);
return new ArrayList<>();
}
}


@Override
public List<FW2> getListOf(List<Predicate> predicateList1, List<Predicate> predicateList2) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory()
.withOptions()
.statementInspector(new CustomInterceptor22())
.openSession()) {

CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<FW2> criteria = builder.createQuery(FW2.class);
Root<FW2> root = criteria.from(FW2.class);

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
return "FW2";
}
}
