package com.company.dao;

import com.company.models.SheetName;
import org.hibernate.criterion.Restrictions;

import javax.persistence.criteria.Predicate;
import java.util.List;




public interface SheetNameDao extends Dao<SheetName, String> {
@Override
void update(SheetName t);
@Override
void add(SheetName t);
@Override
void addLots(List<SheetName> t);
@Override
void delete(SheetName t);
@Override
SheetName get(String id);
@Override
List<SheetName> getListOf();

List<SheetName> getListOf(List<Restrictions> t1, List<Predicate> t2);
}
