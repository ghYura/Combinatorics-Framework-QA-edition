package com.company.dao;

import com.company.models.SheetName;
import jakarta.persistence.criteria.Predicate;
import java.util.List;

public interface SheetNameDao extends Dao<SheetName> {
public void update(SheetName t);
public void add(SheetName t);
public void addLots(List<SheetName> t);
public void delete(SheetName t);
public SheetName get(String id);
public List<SheetName> getListOf();
public List<SheetName> getListOf(List<Predicate> t1, List<Predicate> t2);
}
