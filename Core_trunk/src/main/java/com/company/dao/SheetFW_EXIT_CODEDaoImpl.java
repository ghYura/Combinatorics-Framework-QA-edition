package com.company.dao;

import com.company.models.SheetFW_EXIT_CODE;
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

public class SheetFW_EXIT_CODEDaoImpl implements SheetFW_EXIT_CODEDao {

private static final Logger log = LogManager.getLogger(SheetFW_EXIT_CODEDaoImpl.class);

@Override
public void update(SheetFW_EXIT_CODE sheetFW_EXIT_CODE) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.merge(sheetFW_EXIT_CODE);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Update failed", e);
}
}

@Override
public void add(SheetFW_EXIT_CODE sheetFW_EXIT_CODE) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.persist(sheetFW_EXIT_CODE);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Add failed", e);
}
}

@Override
public void addLots(List<SheetFW_EXIT_CODE> sheetFW_EXIT_CODEList) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
for (int i = 0; i < sheetFW_EXIT_CODEList.size(); i++) {
session.persist(sheetFW_EXIT_CODEList.get(i));
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
public void delete(SheetFW_EXIT_CODE sheetFW_EXIT_CODE) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
Transaction tx = session.beginTransaction();
session.remove(sheetFW_EXIT_CODE);
tx.commit();
} catch (Exception e) {
log.error("[REFACTOR9] Delete failed", e);
}
}

@Override
public SheetFW_EXIT_CODE get(long id) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
return session.get(SheetFW_EXIT_CODE.class, id);
}
}

@Override
public SheetFW_EXIT_CODE get(String sheet) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
return session.get(SheetFW_EXIT_CODE.class, sheet);
} catch (Exception e) {
log.error("[REFACTOR9] get(String) failed", e);
return null;
}
}

@Override
public List<SheetFW_EXIT_CODE> getListOf() {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<SheetFW_EXIT_CODE> criteria = builder.createQuery(SheetFW_EXIT_CODE.class);
Root<SheetFW_EXIT_CODE> root = criteria.from(SheetFW_EXIT_CODE.class);
criteria.select(root);
return session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR9] getListOf failed", e);
return new ArrayList<>();
}
}


@Override
public List<SheetFW_EXIT_CODE> getListOf(List<Predicate> t1, List<Predicate> t2) {
try (Session session = HibernateSessionFactoryUtil.getSessionFactory().openSession()) {
CriteriaBuilder builder = session.getCriteriaBuilder();
CriteriaQuery<SheetFW_EXIT_CODE> criteria = builder.createQuery(SheetFW_EXIT_CODE.class);
Root<SheetFW_EXIT_CODE> root = criteria.from(SheetFW_EXIT_CODE.class);

List<Predicate> combined = new ArrayList<>();
if (t1 != null) combined.addAll(t1);
if (t2 != null) combined.addAll(t2);

if (!combined.isEmpty()) {
criteria.where(combined.toArray(new Predicate[0]));
}

return session.createQuery(criteria).getResultList();
} catch (Exception e) {
log.error("[REFACTOR9] Filtered getListOf failed", e);
return new ArrayList<>();
}
}


public String getFriendlyName() {
return "SheetFW_EXIT_CODE";
}
}
