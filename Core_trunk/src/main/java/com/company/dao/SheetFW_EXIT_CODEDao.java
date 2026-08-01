package com.company.dao;

import com.company.models.SheetFW_EXIT_CODE;
import jakarta.persistence.criteria.Predicate;
import java.util.List;

public interface SheetFW_EXIT_CODEDao extends Dao<SheetFW_EXIT_CODE> {
public void update(SheetFW_EXIT_CODE t);
public void add(SheetFW_EXIT_CODE t);
public void addLots(List<SheetFW_EXIT_CODE> t);
public void delete(SheetFW_EXIT_CODE t);
public SheetFW_EXIT_CODE get(String id);
public List<SheetFW_EXIT_CODE> getListOf();
public List<SheetFW_EXIT_CODE> getListOf(List<Predicate> t1, List<Predicate> t2);
}
