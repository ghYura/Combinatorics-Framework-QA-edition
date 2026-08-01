package com.company.models;

import org.hibernate.type.AbstractSingleColumnStandardBasicType;
import org.hibernate.type.descriptor.java.JavaTypeDescriptor;
import org.hibernate.usertype.DynamicParameterizedType;

import java.util.Properties;


public class StringArrayType
extends AbstractSingleColumnStandardBasicType<String[]>
implements DynamicParameterizedType {

public StringArrayType() {
super(ArraySqlTypeDescriptor.INSTANCE, StringArrayTypeDescriptor.INSTANCE);
}

public StringArrayType(JavaTypeDescriptor<String[]> javaTypeDescriptor) {
super(ArraySqlTypeDescriptor.INSTANCE, javaTypeDescriptor);
}

public String getName() {
return "string-array";
}

@Override
protected boolean registerUnderJavaType() {
return true;
}

@Override
public void setParameterValues(Properties parameters) {
((StringArrayTypeDescriptor) getJavaTypeDescriptor()).setParameterValues(parameters);
}
}
