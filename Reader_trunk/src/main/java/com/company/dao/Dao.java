package com.company.dao;

import java.io.Serializable;
import java.util.List;


public interface Dao<T, ID extends Serializable> {

void update(T t);
void add(T t);
void addLots(List<T> t);
void delete(T t);
T get(ID id);
List<T> getListOf();
}
