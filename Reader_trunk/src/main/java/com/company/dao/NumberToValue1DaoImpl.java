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

import com.company.PrintPretty;
import com.company.helpers.CodeLineNumber;
import com.company.helpers.RegexUtils;
import com.company.helpers.Version;
import com.company.models.NumberToValue1;
import com.company.utils.HibernateSessionFactoryUtil;
import org.hibernate.Session;
import org.hibernate.Transaction;

import javax.persistence.criteria.CriteriaBuilder;
import javax.persistence.criteria.CriteriaQuery;
import javax.persistence.criteria.Root;
import java.util.List;

public class NumberToValue1DaoImpl implements NumberToValue1Dao {

@Override
public void update(NumberToValue1 numberToValue1) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();
session.update(numberToValue1);
session.getTransaction().commit();
} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
}

@Override
public void add(NumberToValue1 numberToValue1) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();
session.save(numberToValue1);
session.getTransaction().commit();
} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
}

@Override
public void addLots(List<NumberToValue1> numberToValue1List) {

Session session = null;
Transaction tx = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
tx = session.beginTransaction();

for (int i = 0; i < numberToValue1List.size(); i++) {

session.persist(numberToValue1List.get(i));
if (i % 500 == 0) {

session.flush();
session.clear();
}
}
session.getTransaction().commit();
} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}

}

@Override
public void delete(NumberToValue1 numberToValue1) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();
session.delete(numberToValue1);
session.getTransaction().commit();
} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
}

@Override
public NumberToValue1 get(Short id) {



NumberToValue1 res = null;
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
res = session.get(NumberToValue1.class, id);
} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
return res;
}

@Override
public List<NumberToValue1> getListOf() {
List<NumberToValue1> listOfNum2Vals = null;

Session session = null;



PrintPretty.println(CodeLineNumber.getLineNumber() + " org.hibernate.Version.getVersionString() = " + org.hibernate.Version.getVersionString());
Version curHibernateVersion = new Version(RegexUtils.getFirstRegexStringOf(org.hibernate.Version.getVersionString(), "((\\d)+(\\.(\\d)+)+){1}"));
Version introducedJPAHibernateVersion = new Version("5.2");

if (curHibernateVersion.compareTo(introducedJPAHibernateVersion) >= 0) {

try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();



CriteriaBuilder builder = session.getCriteriaBuilder();

CriteriaQuery<NumberToValue1> criteria = builder.createQuery(NumberToValue1.class);
Root<NumberToValue1> contactRoot = criteria.from(NumberToValue1.class);
criteria.select(contactRoot);
listOfNum2Vals = session.createQuery(criteria).getResultList();

} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}

} else {
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
listOfNum2Vals = session.createCriteria(NumberToValue1.class).list();

} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
}

return listOfNum2Vals;
}
}
