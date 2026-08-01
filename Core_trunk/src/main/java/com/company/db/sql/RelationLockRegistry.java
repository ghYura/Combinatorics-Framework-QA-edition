package com.company.db.sql;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;


public final class RelationLockRegistry {

    private final ConcurrentMap<String, ReadWriteLock> locks = new ConcurrentHashMap<>();


    public ReadWriteLock get(String relation) {
        if (relation == null) throw new IllegalArgumentException("relation must not be null");
        String key = normalizeKey(relation);
        return locks.computeIfAbsent(key, k -> new ReentrantReadWriteLock(true));
    }


    public static String normalizeKey(String relation) {
        if (relation == null) return null;
        String r = relation.replace("\"", "").trim();
        int dot = r.indexOf('.');
        if (dot >= 0) r = r.substring(dot + 1);
        return r;
    }
}
