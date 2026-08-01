package com.company.dao;

import com.company.PrintPretty;
import com.company.helpers.CodeLineNumber;
import com.company.helpers.RegexUtils;
import com.company.helpers.Version;
import com.company.models.SheetName;
import com.company.utils.HibernateSessionFactoryUtil;
import org.hibernate.Session;
import org.hibernate.Transaction;
import org.hibernate.criterion.Restrictions;

import javax.persistence.criteria.CriteriaBuilder;
import javax.persistence.criteria.CriteriaQuery;
import javax.persistence.criteria.Predicate;
import javax.persistence.criteria.Root;
import java.util.List;

public class SheetNameDaoImpl implements SheetNameDao {

@Override
public void update(SheetName sheetName) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();
session.update(sheetName);
session.getTransaction().commit();
} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
}

@Override
public void add(SheetName sheetName) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();
session.save(sheetName);
session.getTransaction().commit();
} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
}

@Override
public void addLots(List<SheetName> sheetNameList) {

Session session = null;
Transaction tx = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
tx = session.beginTransaction();

for (int i = 0; i < sheetNameList.size(); i++) {

session.persist(sheetNameList.get(i));
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
public void delete(SheetName sheetName) {
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
session.beginTransaction();
session.delete(sheetName);
session.getTransaction().commit();
} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
}






@Override
public SheetName get(String sheet) {
SheetName res = null;
Session session = null;
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
res = (SheetName) session.get(SheetName.class, sheet);
} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
return res;
}

@Override
public List<SheetName> getListOf() {
List<SheetName> listOfSheetNames = null;

Session session = null;



PrintPretty.println("class '"+ this.getClass().getName() +"' "+ CodeLineNumber.getLineNumber() + " org.hibernate.Version.getVersionString() = " + org.hibernate.Version.getVersionString());
Version curHibernateVersion = new Version(RegexUtils.getFirstRegexStringOf(org.hibernate.Version.getVersionString(), "((\\d)+(\\.(\\d)+)+){1}"));
Version introducedJPAHibernateVersion = new Version("5.3.7");

if (curHibernateVersion.compareTo(introducedJPAHibernateVersion) >= 0) {

try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();



CriteriaBuilder builder = session.getCriteriaBuilder();

CriteriaQuery<SheetName> criteria = builder.createQuery(SheetName.class);
Root<SheetName> contactRoot = criteria.from(SheetName.class);
criteria.select(contactRoot);
listOfSheetNames = session.createQuery(criteria).getResultList();

} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}

} else {
try {
session = HibernateSessionFactoryUtil.getSessionFactory().openSession();
listOfSheetNames = session.createCriteria(SheetName.class).list();

} catch (Exception e) {
e.printStackTrace();
} finally {
if (session != null && session.isOpen()) session.close();
}
}

return listOfSheetNames;
}

@Override
public List<SheetName> getListOf(List<Restrictions> t1, List<Predicate> t2) {
return null;
}
}
