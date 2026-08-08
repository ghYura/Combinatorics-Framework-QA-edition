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

package com.company.utils;
import com.company.ReaderConfig;

import com.company.Main;
import com.company.dao.Dao;
import com.company.dao.NumberToValue1DaoImpl;
import com.company.models.*;
import org.hibernate.SessionFactory;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;
import org.hibernate.cfg.Configuration;

public class HibernateSessionFactoryUtil {
private static SessionFactory sessionFactory;

public Dao<NumberToValue1, Short> dao;

private HibernateSessionFactoryUtil() {}

public static SessionFactory getSessionFactory() {
if (sessionFactory == null) {
try {

Configuration configuration = new Configuration().mergeProperties(ReaderConfig.prop).configure("hibernate.cfg.xml");
configuration.addAnnotatedClass(NumberToValue1.class);

configuration.addAnnotatedClass(SheetName.class);

configuration.addAnnotatedClass(BaseEntity.class);
StandardServiceRegistryBuilder builder = new StandardServiceRegistryBuilder().applySettings(configuration.getProperties());
sessionFactory = configuration.buildSessionFactory(builder.build());

} catch (Exception e) {
System.out.println("Exception in utils.HibernateSessionFactoryUtil!" + e);
}
}
return sessionFactory;
}

public Dao<NumberToValue1, Short> getDao(){
if (dao == null) dao = new NumberToValue1DaoImpl();
return dao;
}
}
