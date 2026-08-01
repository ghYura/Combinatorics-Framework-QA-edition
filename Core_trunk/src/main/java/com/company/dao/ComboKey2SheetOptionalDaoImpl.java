package com.company.dao;

import com.company.models.ComboKey2SheetOptional;
import com.company.utils.HibernateSessionFactoryUtil;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.hibernate.Session;

import java.util.List;

public class ComboKey2SheetOptionalDaoImpl implements ComboKey2SheetOptionalDao {

private static final Logger log = LogManager.getLogger(ComboKey2SheetOptionalDaoImpl.class);

@Override
public void update(ComboKey2SheetOptional comboKey2SheetOptional) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();

session.merge(comboKey2SheetOptional);
session.getTransaction().commit();
} catch (Exception e) {
log.error("[REFACTOR-FIX] Exception in update", e);
} finally {
if (session != null && session.isOpen()) session.close();
}
}

public void addArrArr(ComboKey2SheetOptional comboKey2SheetOptional) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();

session.persist(comboKey2SheetOptional);
session.getTransaction().commit();
} catch (Exception e) {
log.error("[REFACTOR-FIX] Exception in addArrArr", e);
} finally {
if (session != null && session.isOpen()) session.close();
}
}

@Override
public void add(ComboKey2SheetOptional comboKey2SheetOptional) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();
session.persist(comboKey2SheetOptional);
session.getTransaction().commit();
} catch (Exception e) {
log.error("[REFACTOR-FIX] Exception in add", e);
} finally {
if (session != null && session.isOpen()) session.close();
}
}

@Override
public void addLots(List<ComboKey2SheetOptional> comboKey2SheetOptionalList) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();

for (int i = 0; i < comboKey2SheetOptionalList.size(); i++) {
session.persist(comboKey2SheetOptionalList.get(i));
if (i % 500 == 0) {
session.flush();
session.clear();
}
}
session.getTransaction().commit();
} catch (Exception e) {
log.error("[REFACTOR-FIX] Exception in addLots", e);
} finally {
if (session != null && session.isOpen()) session.close();
}
}

@Override
public void delete(ComboKey2SheetOptional comboKey2SheetOptional) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();

session.remove(comboKey2SheetOptional);
session.getTransaction().commit();
} catch (Exception e) {
log.error("[REFACTOR-FIX] Exception in delete", e);
} finally {
if (session != null && session.isOpen()) session.close();
}
}

@Override
public ComboKey2SheetOptional get(long id) {
ComboKey2SheetOptional res = null;
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();

res = session.find(ComboKey2SheetOptional.class, id);
} catch (Exception e) {
log.error("[REFACTOR-FIX] Exception in get", e);
} finally {
if (session != null && session.isOpen()) session.close();
}
return res;
}

@Override
public List<ComboKey2SheetOptional> getListOf() {
List<ComboKey2SheetOptional> listOfCombos = null;
Session session = null;

try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<ComboKey2SheetOptional> criteria = builder.createQuery(ComboKey2SheetOptional.class);
Root<ComboKey2SheetOptional> root = criteria.from(ComboKey2SheetOptional.class);
criteria.select(root);

listOfCombos = session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR-FIX] Exception in getListOf", e);
} finally {
if (session != null && session.isOpen()) session.close();
}

return listOfCombos;
}


@Override
public List<ComboKey2SheetOptional> getListOf(List<Predicate> t1, List<Predicate> t2) {

return null;
}
}
