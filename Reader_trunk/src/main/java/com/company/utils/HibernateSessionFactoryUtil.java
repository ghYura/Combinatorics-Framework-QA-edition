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
