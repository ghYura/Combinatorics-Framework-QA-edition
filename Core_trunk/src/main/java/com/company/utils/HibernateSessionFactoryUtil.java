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

package com.company.utils;

import com.company.dao.Dao;
import com.company.dao.NumberToValue1DaoImpl;
import com.company.models.*;
import com.company.models.ComboKey2SheetOptional;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.hibernate.SessionFactory;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;
import org.hibernate.cfg.Configuration;

import java.util.Properties;


public class HibernateSessionFactoryUtil {

private static final Logger log = LogManager.getLogger(HibernateSessionFactoryUtil.class);

private static volatile SessionFactory sessionFactory;
private static volatile int            workerCount    = 1;
private static volatile Properties     hibernateProps = null;





private static volatile boolean        buildFailed    = false;

public Dao dao;

private HibernateSessionFactoryUtil() { }


public static void init(int configuredWorkerCount, Properties props) {
workerCount    = configuredWorkerCount;
hibernateProps = props;
log.info("HibernateSessionFactoryUtil initialised: workerCount={}", configuredWorkerCount);
}


public static void buildEager() {
SessionFactory sf = getSessionFactory();
if (sf == null) {
throw new IllegalStateException(
"[REFACTOR12] Hibernate SessionFactory could not be built. " +
"Check the errors above and fix hibernate.cfg.xml / bigintValue.hbm.xml " +
"before attempting to run the application.");
}
log.info("[REFACTOR12] SessionFactory built eagerly and ready");
}

public static SessionFactory getSessionFactory() {
if (buildFailed) return null;
if (workerCount > 1) return getSessionFactoryDblChkLock();
if (sessionFactory == null) {
sessionFactory = buildSessionFactory();
}
return sessionFactory;
}

public static SessionFactory getSessionFactoryDblChkLock() {
if (buildFailed) return null;
if (sessionFactory == null) {
synchronized (HibernateSessionFactoryUtil.class) {
if (sessionFactory == null) {
sessionFactory = buildSessionFactory();
}
}
}
return sessionFactory;
}

private static SessionFactory buildSessionFactory() {
try {

Configuration configuration = new Configuration();



configuration.configure();



if (hibernateProps != null) {
log.info("Applying dynamic database configuration from fw.properties");
configuration.addProperties(hibernateProps);
}



configuration.setProperty("hibernate.transform_hbm_xml.enabled", "true");





configuration.addAnnotatedClass(NumberToValue1.class);
configuration.addAnnotatedClass(SheetName.class);
configuration.addAnnotatedClass(FW_CUSTOM_VAR.class);
configuration.addAnnotatedClass(SheetFW_EXIT_CODE.class);
configuration.addAnnotatedClass(FW.class);
configuration.addAnnotatedClass(FW2.class);
configuration.addAnnotatedClass(BaseEntity.class);
configuration.addAnnotatedClass(ComboKey2SheetOptional.class);




SessionFactory sf = configuration.buildSessionFactory();

log.info("Hibernate SessionFactory built successfully");
return sf;

} catch (Exception e) {
buildFailed = true;
log.error("Failed to build Hibernate SessionFactory. " +
"Check if 'bigintValue.hbm.xml' uses full type names (e.g. java.lang.String)", e);
return null;
}
}

public Dao getDao() {
if (dao == null) dao = new NumberToValue1DaoImpl();
return dao;
}
}
