package com.company.models;

import org.hibernate.type.AbstractSingleColumnStandardBasicType;
import org.hibernate.usertype.DynamicParameterizedType;

import java.util.Properties;

public class ArrayArrayType
extends AbstractSingleColumnStandardBasicType<Long[][]>
implements DynamicParameterizedType {

public static final ArrayArrayType INSTANCE = new ArrayArrayType();

public ArrayArrayType() {
super(ArraySqlTypeDescriptor.INSTANCE, ArrayArrayTypeDescriptor.INSTANCE);
}

public String getName() {
return "long-array-array";
}

@Override
protected boolean registerUnderJavaType () {
return true;
}

@Override
public void setParameterValues (Properties parameters){
((ArrayArrayTypeDescriptor) getJavaTypeDescriptor()).setParameterValues(parameters);
}
}
