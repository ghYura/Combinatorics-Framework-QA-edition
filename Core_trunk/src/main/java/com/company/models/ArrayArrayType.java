package com.company.models;

import org.hibernate.type.AbstractSingleColumnStandardBasicType;
import org.hibernate.usertype.DynamicParameterizedType;
import org.hibernate.type.descriptor.jdbc.JdbcType;
import org.hibernate.type.descriptor.java.JavaType;

import java.util.Properties;

public class ArrayArrayType
extends AbstractSingleColumnStandardBasicType<Long[][]>
implements DynamicParameterizedType {

public static final ArrayArrayType INSTANCE = new ArrayArrayType();

public ArrayArrayType() {

super(
(JdbcType) ArraySqlTypeDescriptor.INSTANCE,
(JavaType<Long[][]>) ArrayArrayTypeDescriptor.INSTANCE
);
}

@Override
public String getName() {
return "long-array-array";
}

@Override
public void setParameterValues(Properties parameters) {

Object jType = getJavaType();


if (jType instanceof DynamicParameterizedType dynamicType) {
dynamicType.setParameterValues(parameters);
}
}
}
