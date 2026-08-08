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

import com.company.models.NumberToValue1;
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

public class NumberToValue1DaoImpl implements NumberToValue1Dao {

private static final Logger log = LogManager.getLogger(NumberToValue1DaoImpl.class);

@Override
public void update(NumberToValue1 numberToValue1) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.merge(numberToValue1);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in update", e);
}
}

@Override
public void add(NumberToValue1 numberToValue1) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.persist(numberToValue1);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in add", e);
}
}

@Override
public void addLots(List<NumberToValue1> numberToValue1List) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
for (int i = 0; i < numberToValue1List.size(); i++) {
session.persist(numberToValue1List.get(i));
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
public void delete(NumberToValue1 numberToValue1) {

try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.remove(numberToValue1);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in delete", e);
}
}

@Override
public NumberToValue1 get(long id) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
return session.get(NumberToValue1.class, id);
}
}


public NumberToValue1 get(short id) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
return session.get(NumberToValue1.class, (long)id);
}
}

@Override
public List<NumberToValue1> getListOf() {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<NumberToValue1> criteria = builder.createQuery(NumberToValue1.class);
Root<NumberToValue1> root = criteria.from(NumberToValue1.class);
criteria.select(root);
return session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR9] Exception in getListOf", e);
return new ArrayList<>();
}
}


@Override
public List<NumberToValue1> getListOf(List<Predicate> t1, List<Predicate> t2) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<NumberToValue1> criteria = builder.createQuery(NumberToValue1.class);
Root<NumberToValue1> root = criteria.from(NumberToValue1.class);

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
return "NumberToValue1";
}
}
