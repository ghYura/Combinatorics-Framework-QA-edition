package com.company.models;

import org.hibernate.type.AbstractSingleColumnStandardBasicType;
import org.hibernate.type.descriptor.java.JavaType;
import org.hibernate.type.descriptor.jdbc.JdbcType;
import org.hibernate.usertype.DynamicParameterizedType;

import java.util.Properties;


public class StringArrayType
extends AbstractSingleColumnStandardBasicType<String[]>
implements DynamicParameterizedType {

public static final StringArrayType INSTANCE = new StringArrayType();

public StringArrayType() {
super(
(JdbcType) ArraySqlTypeDescriptor.INSTANCE,
(JavaType<String[]>) StringArrayTypeDescriptor.INSTANCE
);
}

public StringArrayType(JavaType<String[]> javaType) {
super(
(JdbcType) ArraySqlTypeDescriptor.INSTANCE,
javaType
);
}

@Override
public String getName() {
return "string-array";
}

@Override
protected boolean registerUnderJavaType() {
return true;
}

@Override
public void setParameterValues(Properties parameters) {


Object jType = getJavaType();

if (jType instanceof DynamicParameterizedType dynamicType) {
dynamicType.setParameterValues(parameters);
} else {

StringArrayTypeDescriptor.INSTANCE.setParameterValues(parameters);
}
}
}
