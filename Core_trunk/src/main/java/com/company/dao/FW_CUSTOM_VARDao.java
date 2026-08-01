package com.company.dao;

import com.company.models.FW_CUSTOM_VAR;
import jakarta.persistence.criteria.Predicate;
import java.util.List;

public interface FW_CUSTOM_VARDao extends Dao<FW_CUSTOM_VAR> {
public void update(FW_CUSTOM_VAR t);
public void add(FW_CUSTOM_VAR t);
public void addLots(List<FW_CUSTOM_VAR> t);
public void delete(FW_CUSTOM_VAR t);
public FW_CUSTOM_VAR get(Integer id);
public List<FW_CUSTOM_VAR> getListOf();
public List<FW_CUSTOM_VAR> getListOf(List<Predicate> t1, List<Predicate> t2);
}
