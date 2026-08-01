package com.company.dao;



import jakarta.persistence.criteria.Predicate;
import java.util.List;

public interface Dao<T> {

void update(T t);
void add(T t);
void addLots(List<T> t);
void delete(T t);
T get(long id);
List<T> getListOf();


List<T> getListOf(List<Predicate> t1, List<Predicate> t2);
}
